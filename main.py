import datetime
import httpx
from fastapi import FastAPI, status, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, CheckConstraint,create_engine, text
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import OperationalError
from sqlalchemy import select
import logging
import os
import sys

logger = logging.getLogger("feedback_service")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(levelname)s: %(asctime)s | %(name)s | %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@db:5432/rating_db")

app = FastAPI(title="Feedback Service")
engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class RatingModel(Base):
    __tablename__ = "ratings"
    
    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer)
    rider_id = Column(Integer, index=True)
    driver_id = Column(Integer)
    rating = Column(Integer)
    comment = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint('rating >= 1 AND rating <= 5', name='check_rating_range'),
    )

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.info(f"Database transaction error: {e}", exc_info=True)
        raise e
    finally:
        db.close()


class RatingCreate(BaseModel):
    trip_id: int
    rider_id: int
    driver_id: int
    rating: int
    comment: str | None = None

class Rating(RatingCreate):
    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    
    class Config:
        orm_mode = True

TRIP_SERVICE_URL = "http://trip-service:8002/v1/trips/"
RIDER_SERVICE_URL = "http://rider-service:8000/v1/riders/"


async def is_trip_completed(trip_id: int) -> bool:
    url = f"{TRIP_SERVICE_URL}{trip_id}"
    logger.info(f"[TRIP-SERVICE] Attempting GET: {url}")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{TRIP_SERVICE_URL}{trip_id}")
        if response.status_code == 200:
            logger.info(f"[TRIP-SERVICE] Response Status: {response.status_code}")
            trip_data = response.json()
            status_val = trip_data.get("status")
            logger.info(f"[TRIP-SERVICE] Trip Status: {status_val}")
            return status_val == "COMPLETED"
        logger.info(f"[TRIP-SERVICE] Trip ID {trip_id} not found or invalid status ({response.status_code}).")
        return False

async def is_rider(rider_id: int) -> bool:
    url = f"{RIDER_SERVICE_URL}{rider_id}"
    logger.info(f"[RIDER-SERVICE] Attempting GET: {url}")
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        logger.info(f"[RIDER-SERVICE] Response Status: {response.status_code}")
        if response.status_code == 200:
            logger.info(f"[RIDER-SERVICE] Rider ID {rider_id} found successfully.")
            return True
        else:
            logger.warning(f"[RIDER-SERVICE] Rider ID {rider_id} NOT found. Status Code: {response.status_code}. Response Body: {response.text}")
            return False
        
@app.get("/health", status_code=status.HTTP_200_OK)
def health_check(db: Session = Depends(get_db)):
    health_status = {"status": "ok", "database": "ok"}
    try:
        db.execute(text("SELECT 1"))
    except OperationalError as e:
        logger.error(f"Health Check Failed: Database connection error. {e}", exc_info=True)
        health_status["database"] = "unhealthy"
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=health_status)
    except Exception as e:
        logger.error(f"Health Check Failed: Unexpected database error. {e}", exc_info=True)
        health_status["database"] = "unhealthy"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=health_status)
    logger.info("Health check passed.")
    return health_status


@app.get("/v1/ratings", response_model=list[Rating], status_code=status.HTTP_200_OK)
def get_all_ratings(db: Session = Depends(get_db)):
    logger.info("GET /v1/ratings called: Fetching all ratings.")
    try:
        ratings = db.query(RatingModel).all()
        logger.info(f"Retrieved {len(ratings)} ratings.")
        return ratings
    except Exception as e:
        logger.error(f"Error fetching all ratings: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail="Failed to retrieve ratings from the database.")

@app.get("/v1/ratings/{rating_id}", response_model=Rating, status_code=status.HTTP_200_OK)
def get_specific_rating(rating_id: int, db: Session = Depends(get_db)):
    logger.info(f"GET /v1/ratings/{rating_id} called.")
    rating = db.query(RatingModel).filter(RatingModel.id == rating_id).first()    
    if not rating:
        logger.warning(f"Rating ID {rating_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rating with ID {rating_id} not found")
    logger.info(f"Successfully retrieved rating ID {rating_id}.")
    return rating

@app.post("/v1/ratings", response_model=Rating, status_code=status.HTTP_201_CREATED)
async def create_rating(rating: RatingCreate, db: Session = Depends(get_db)):
    logger.info(f"--- POST /v1/ratings initiated for rider_id: {rating.rider_id} ---")
    rider_exists = await is_rider(rating.rider_id)
    logger.info(f'Rider existence check result: {rider_exists}')
    if not rider_exists:
        logger.warning(f"Request failed: Rider ID {rating.rider_id} not found.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No such rider found")
    # if not is_trip_completed(rating.trip_id):
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trip is not completed yet")
    try: 
        db_rating = RatingModel(**rating.dict())
        db.add(db_rating)
        db.commit()
        db.refresh(db_rating)
    except Exception as e:
        logger.info(f"Failed to commit rating to database: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not save rating to database.")
    logger.info(f"Rating successfully created for ID: {db_rating.id}")
    return db_rating