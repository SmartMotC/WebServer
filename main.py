from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_
from core.database import get_db, get_votes_db
from core.database import User, Vote, VoteResult, MemeLike
import os
import shutil
from datetime import datetime

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/", tags=["Test"])
async def get_start():
    return {"message": f"🔥 TEST {datetime.now()}"}


@app.get("/users/all_users", tags=["AdminPanel"])
async def get_all_users(db1: Session = Depends(get_db)):
    users = db1.query(User).all()
    return users


@app.get("/users/profile/{user_id}", tags=["Users"])
async def get_user_profile(user_id: int, db1: Session = Depends(get_db)):
    user = db1.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Получаем голосования пользователя из votes.db
    db_votes = next(get_votes_db())
    try:
        user_votes = db_votes.query(VoteResult).filter(VoteResult.user_id == user_id).all()
        votes_data = []
        for vote in user_votes:
            vote_info = db_votes.query(Vote).filter(Vote.id == vote.vote_id).first()
            votes_data.append({
                "vote_id": vote.vote_id,
                "category": vote_info.category if vote_info else "Неизвестно",
                "photo_choice": vote.photo_choice,
                "created_at": vote.created_at.isoformat() if vote.created_at else None
            })
    finally:
        db_votes.close()

    return {
        "id": user.id,
        "name": user.name,
        "grade": user.grade,
        "votes": votes_data
    }


@app.post("/users/register", tags=["Registration"])
async def add_users(name: str, grade: int, db1: Session = Depends(get_db)):
    if grade < 1 or grade > 11:
        raise HTTPException(status_code=400, detail="Класс должен быть от 1 до 11")
    user = User(name=name, grade=grade)
    db1.add(user)
    db1.commit()
    db1.refresh(user)
    return user


@app.post("/users/login", tags=["Registration"])
async def login_user(name: str, grade: int, db1: Session = Depends(get_db)):
    """🔑 Вход: проверка ученика по имени + классу"""
    user = db1.query(User).filter(
        and_(User.name == name, User.grade == grade)
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="👤 Ученик не найден! Зарегистрируйтесь")

    return {
        "message": "✅ Вход успешен!",
        "user_id": user.id,
        "name": user.name,
        "grade": user.grade
    }


@app.post("/users/delete_users", tags=["AdminPanel"])
async def delete_users(id: int, db1: Session = Depends(get_db)):
    user = db1.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="👤 Пользователь не найден")

    db1.delete(user)
    db1.commit()
    return {"message": "✅ Пользователь удален"}


@app.post("/admin/check", tags=["Admin"])
async def check_admin(password: str):
    if password == "321":
        return {"access": True}
    raise HTTPException(status_code=403, detail="Неверный пароль")


@app.post("/vote/add_votes", tags=["AdminPanel"])
async def add_vote(
        category: str,
        photo1: UploadFile = File(...),
        photo2: UploadFile = File(...),
        photo3: UploadFile = File(...),
        db2: Session = Depends(get_votes_db)
):
    try:
        os.makedirs("static/votes", exist_ok=True)
        timestamp = int(datetime.now().timestamp())
        photos = []

        for i, photo in enumerate([photo1, photo2, photo3], 1):
            if not photo:
                raise HTTPException(status_code=400, detail=f"Фото {i} обязательно!")

            ext = photo.filename.split('.')[-1].lower() if '.' in photo.filename else 'jpg'
            if ext not in ['jpg', 'jpeg', 'png']:
                raise HTTPException(status_code=400, detail=f"Поддерживаются только JPG/PNG для фото {i}")

            filename = f"{category}_photo{i}_{timestamp}.{ext}"
            path = f"static/votes/{filename}"

            with open(path, "wb") as buffer:
                shutil.copyfileobj(photo.file, buffer)
            photos.append(path)

        vote = Vote(
            category=category,
            photo1_path=photos[0],
            photo2_path=photos[1],
            photo3_path=photos[2],
            ip_address="127.0.0.1"
        )

        db2.add(vote)
        db2.commit()
        db2.refresh(vote)

        return {
            "message": "✅ Голосование добавлено с 3 фото!",
            "vote_id": vote.id,
            "category": vote.category,
            "photos": [f"/{p}" for p in photos]
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db2.rollback()
        raise HTTPException(status_code=500, detail="❌ Ошибка сохранения в БД")
    except Exception as e:
        db2.rollback()
        raise HTTPException(status_code=500, detail="❌ Ошибка сервера")


@app.get("/vote/get_votes", tags=["Users"])
async def get_all_votes(db2: Session = Depends(get_votes_db)):
    try:
        votes = db2.query(Vote).filter(Vote.photo2_path.isnot(None)).all()  # Только голосования (не мемы)
        result = []
        for v in votes:
            # Получаем статистику голосов
            results = db2.query(VoteResult).filter(VoteResult.vote_id == v.id).all()
            votes_count = {1: 0, 2: 0, 3: 0}
            for r in results:
                votes_count[r.photo_choice] += 1

            result.append({
                "id": v.id,
                "category": v.category,
                "photo1_path": v.photo1_path,
                "photo2_path": v.photo2_path,
                "photo3_path": v.photo3_path,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "results": votes_count,
                "total_votes": len(results)
            })
        return result
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="❌ Ошибка получения голосований")


@app.post("/vote/delete_votes", tags=["AdminPanel"])
async def delete_votes(id: int, db2: Session = Depends(get_votes_db)):
    try:
        vote = db2.query(Vote).filter(Vote.id == id).first()
        if not vote:
            raise HTTPException(status_code=404, detail="📤 Голосование не найдено")

        for path in [vote.photo1_path, vote.photo2_path, vote.photo3_path]:
            if path:
                full_path = f"static/{path.lstrip('/')}"
                if os.path.exists(full_path):
                    os.remove(full_path)

        db2.delete(vote)
        db2.commit()
        return {"message": "✅ Голосование удалено с файлами"}

    except HTTPException:
        raise
    except SQLAlchemyError:
        db2.rollback()
        raise HTTPException(status_code=500, detail="❌ Ошибка удаления из БД")


@app.post("/vote/{vote_id}/vote", tags=["Voting"])
async def cast_vote(
        vote_id: int,
        photo_choice: int,
        user_id: int,
        db_votes: Session = Depends(get_votes_db)
):
    vote = db_votes.query(Vote).filter(Vote.id == vote_id).first()
    if not vote:
        raise HTTPException(status_code=404, detail="📤 Голосование не найдено")

    if photo_choice not in [1, 2, 3]:
        raise HTTPException(status_code=400, detail="❌ Выберите фото 1, 2 или 3!")

    existing_vote = db_votes.query(VoteResult).filter(
        VoteResult.vote_id == vote_id,
        VoteResult.user_id == user_id
    ).first()

    if existing_vote:
        raise HTTPException(status_code=400, detail="⏰ Вы уже голосовали!")

    try:
        new_vote = VoteResult(
            vote_id=vote_id,
            user_id=user_id,
            photo_choice=photo_choice
        )

        db_votes.add(new_vote)
        db_votes.commit()
        db_votes.refresh(new_vote)

        return {
            "message": "✅ Голос учтен!",
            "your_choice": photo_choice,
            "vote_id": new_vote.id
        }

    except SQLAlchemyError:
        db_votes.rollback()
        raise HTTPException(status_code=500, detail="❌ Ошибка сохранения голоса")


@app.post("/memes/add", tags=["Memes"])
async def add_meme(
        category: str,
        description: str,
        user_id: int,
        file: UploadFile = File(...),
        db: Session = Depends(get_votes_db)
):
    try:
        os.makedirs("static/memes", exist_ok=True)
        timestamp = int(datetime.now().timestamp())

        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
        allowed = ['jpg', 'jpeg', 'png', 'gif', 'mp4', 'webm', 'avi', 'mov']
        if ext not in allowed:
            raise HTTPException(status_code=400, detail=f"❌ Только {', '.join(allowed)}")

        filename = f"meme_{category}_{timestamp}.{ext}"
        path = f"static/memes/{filename}"

        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        meme = Vote(
            category=f"MEME_{category}",
            photo1_path=path,
            photo2_path=None,
            photo3_path=None,
            ip_address=f"{description}|{user_id}"  # Храним описание и ID автора
        )

        db.add(meme)
        db.commit()
        db.refresh(meme)

        return {
            "message": "✅ Мем добавлен! 😂",
            "meme_id": meme.id,
            "url": f"/{path}",
            "category": category,
            "description": description
        }
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="❌ Ошибка БД")


@app.get("/memes/all", tags=["Memes"])
async def get_all_memes(db: Session = Depends(get_votes_db)):
    memes = db.query(Vote).filter(
        Vote.category.like("MEME_%"),
        Vote.photo2_path.is_(None)
    ).all()

    result = []
    for m in memes:
        # Получаем описание и ID автора
        desc_parts = m.ip_address.split('|') if m.ip_address else ["", ""]
        description = desc_parts[0] if len(desc_parts) > 0 else ""
        author_id = int(desc_parts[1]) if len(desc_parts) > 1 and desc_parts[1].isdigit() else None

        # Получаем лайки
        likes = db.query(MemeLike).filter(MemeLike.meme_id == m.id).count()

        result.append({
            "id": m.id,
            "category": m.category[5:],
            "url": f"/{m.photo1_path}",
            "description": description,
            "author_id": author_id,
            "likes": likes,
            "created_at": m.created_at.isoformat() if m.created_at else None
        })

    return result


@app.post("/memes/{meme_id}/like", tags=["Memes"])
async def like_meme(meme_id: int, user_id: int, db: Session = Depends(get_votes_db)):
    # Проверяем существование мема
    meme = db.query(Vote).filter(Vote.id == meme_id).first()
    if not meme or not meme.category.startswith("MEME_"):
        raise HTTPException(status_code=404, detail="Мем не найден")

    # Проверяем, не ставил ли пользователь уже лайк
    existing_like = db.query(MemeLike).filter(
        MemeLike.meme_id == meme_id,
        MemeLike.user_id == user_id
    ).first()

    if existing_like:
        # Убираем лайк
        db.delete(existing_like)
        db.commit()
        return {"liked": False, "likes": db.query(MemeLike).filter(MemeLike.meme_id == meme_id).count()}
    else:
        # Ставим лайк
        new_like = MemeLike(meme_id=meme_id, user_id=user_id)
        db.add(new_like)
        db.commit()
        return {"liked": True, "likes": db.query(MemeLike).filter(MemeLike.meme_id == meme_id).count()}


@app.delete("/memes/delete/{meme_id}", tags=["AdminPanel"])
async def delete_meme(meme_id: int, db: Session = Depends(get_votes_db)):
    meme = db.query(Vote).filter(Vote.id == meme_id).first()
    if not meme:
        raise HTTPException(status_code=404, detail="😂 Мем не найден")

    if os.path.exists(meme.photo1_path):
        os.remove(meme.photo1_path)

    # Удаляем связанные лайки
    db.query(MemeLike).filter(MemeLike.meme_id == meme_id).delete()
    db.delete(meme)
    db.commit()
    return {"message": "✅ Мем удален 😂"}
