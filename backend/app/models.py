# backend/app/models.py
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base

class EWNodeModel(Base):
    __tablename__ = "ew_nodes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    alt = Column(Float, default=10.0)
    max_range = Column(Float, default=3500.0)      # Максимальний радіус дії (м)
    beamwidth = Column(Float, default=30.0)        # Сектор придушення (градуси)
    current_azimuth = Column(Float, default=0.0)   # Азимут наведення (градуси)
    current_elevation = Column(Float, default=15.0)
    is_armed = Column(Boolean, default=False)
    is_transmitting = Column(Boolean, default=False)

class TacticalZoneModel(Base):
    __tablename__ = "tactical_zones"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    zone_type = Column(String, nullable=False)  # "danger" або "safe"
    # Геометрія полігону у форматі JSON-рядка [[lat, lon], [lat, lon], ...]
    coordinates = Column(Text, nullable=False)

class TacticalSensorModel(Base):
    __tablename__ = "tactical_sensors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    sensor_type = Column(String, nullable=False) # "camera", "acoustic", "observation_post", "witness_report", "target_asset"
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    alt = Column(Float, default=0.0)
    detection_radius = Column(Float, default=1000.0) # Радіус виявлення / засікання (м)
    description = Column(String, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DetectionEvent(Base):
    __tablename__ = "detection_events"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(String, index=True)
    sensor_type = Column(String)  # acoustic, optical, crowdsource
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    alt = Column(Float, default=150.0)
    confidence = Column(Float, default=0.8)
    created_at = Column(DateTime(timezone=True), server_default=func.now())