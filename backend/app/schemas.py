# backend/app/schemas.py
from pydantic import BaseModel
from typing import List, Optional

class DetectionCreate(BaseModel):
    sensor_id: str
    sensor_type: str
    lat: float
    lon: float
    alt: float = 150.0
    confidence: float = 0.85

class EWNodeCreate(BaseModel):
    name: str
    lat: float
    lon: float
    alt: float = 10.0
    max_range: float = 3500.0
    beamwidth: float = 30.0
    current_azimuth: float = 0.0

class EWNodeUpdate(BaseModel):
    name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt: Optional[float] = None
    current_azimuth: Optional[float] = None
    beamwidth: Optional[float] = None
    max_range: Optional[float] = None

class TacticalZoneCreate(BaseModel):
    name: str
    zone_type: str  # "danger" | "safe"
    coordinates: List[List[float]]  # [[lat, lon], ...]

class TacticalZoneUpdate(BaseModel):
    name: Optional[str] = None
    zone_type: Optional[str] = None
    coordinates: Optional[List[List[float]]] = None

class TacticalSensorCreate(BaseModel):
    name: str
    sensor_type: str  # "camera" | "acoustic" | "observation_post" | "witness_report" | "target_asset"
    lat: float
    lon: float
    alt: float = 0.0
    detection_radius: float = 1500.0
    description: Optional[str] = ""

class TacticalSensorUpdate(BaseModel):
    name: Optional[str] = None
    sensor_type: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt: Optional[float] = None
    detection_radius: Optional[float] = None
    description: Optional[str] = None

class ArmEWCommand(BaseModel):
    node_id: int
    arm: bool
    burst_duration: int = 20