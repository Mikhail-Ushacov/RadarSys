// frontend/src/types.ts
export interface Track {
  id: string;
  lat: number;
  lon: number;
  alt: number;
  speed: number;
  heading: number;
  predicted_30s: [number, number];
  predicted_60s: [number, number];
  crash_point: [number, number];
  is_safe_to_engage: boolean;
}

export interface EWNode {
  id: number;
  name: string;
  lat: number;
  lon: number;
  azimuth: number;
  beamwidth: number;
  max_range: number;
  is_armed: boolean;
  is_transmitting: boolean;
}

export interface TacticalZone {
  id: number;
  name: string;
  zone_type: 'safe' | 'danger';
  coordinates: [number, number][];
}

export type SensorType = 
  | 'camera' 
  | 'acoustic' 
  | 'observation_post' 
  | 'witness_report' 
  | 'target_asset';

export interface TacticalSensor {
  id: number;
  name: string;
  sensor_type: SensorType;
  lat: number;
  lon: number;
  detection_radius: number;
  description?: string;
}

export interface TacticalUpdate {
  tracks: Track[];
  ew_nodes: EWNode[];
  zones: TacticalZone[];
  sensors: TacticalSensor[];
  timestamp: number;
}