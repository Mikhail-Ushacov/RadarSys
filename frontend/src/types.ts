// frontend/src/types.ts

export type DetectionStage = 'INITIAL_CONTACT' | 'TRACKED';

export interface ActiveEvent {
  id: number;
  type: 'witness_call' | 'sensor_alert';
  title: string;
  message: string;
  lat: number;
  lon: number;
  time: number;
}

export interface Track {
  id: string;
  status?: 'CRUISING' | 'JAMMED' | 'CRASHED' | 'DETECTING';
  detection_stage?: 'INITIAL_CONTACT' | 'TRACKED';
  detection_count?: number;
  last_sensor?: string;
  detection_timeline?: string[];
  kinematics_note?: string;
  lat: number;
  lon: number;
  alt: number;
  speed: number | null;
  heading: number | null;
  predicted_30s?: [number, number] | null;
  predicted_60s?: [number, number] | null;
  crash_point?: [number, number] | null;
  crash_safety?: number | null;
  corridor_safety?: number | null;
  impact_ellipse?: [number, number][] | null;
  is_safe_to_engage: boolean;
  is_ci_critical?: boolean;
  ci_distance?: number | null;
  nearest_ci?: string | null;
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

export type ZoneType = 'safe' | 'caution' | 'danger';

export interface TacticalZone {
  id: number;
  name: string;
  zone_type: ZoneType;
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
  active_events?: ActiveEvent[];
  timestamp: number;
  simulation_active?: boolean;
  auto_tracking?: boolean;
  emergency_override?: boolean;
  threat_info?: string | null;
  recent_downed?: DownedDroneDetailed[];
  total_downed_count?: number;
}