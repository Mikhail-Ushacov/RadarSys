// frontend/src/types.ts
export interface Track {
  id: string;
  status?: 'CRUISING' | 'JAMMED' | 'CRASHED';
  lat: number;
  lon: number;
  alt: number;
  speed: number;
  heading: number;
  predicted_30s: [number, number];
  predicted_60s: [number, number];
  crash_point: [number, number];
  is_safe_to_engage: boolean;
  is_ci_critical?: boolean;
  ci_distance?: number;
  nearest_ci?: string;
  target_asset_name?: string;
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
  target_lead_coord?: [number, number] | null;
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

export interface DownedDroneDetailed {
  id: number;
  drone_id: string;
  spawn_time: string;
  downed_time: string;
  spawn_coords: string;
  target_name: string;
  interceptor_name: string;
  crash_coords: string;
  crash_zone: string;
  status: string;
}

export interface TacticalUpdate {
  tracks: Track[];
  ew_nodes: EWNode[];
  zones: TacticalZone[];
  sensors: TacticalSensor[];
  timestamp: number;
  simulation_active?: boolean;
  auto_tracking?: boolean;
  emergency_override?: boolean;
  threat_info?: string | null;
  recent_downed?: DownedDroneDetailed[];
  total_downed_count?: number;
}