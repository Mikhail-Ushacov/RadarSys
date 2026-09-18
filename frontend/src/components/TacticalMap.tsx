// frontend/src/components/TacticalMap.tsx
import React, { useState, useRef, useMemo } from 'react';
import { 
  MapContainer, TileLayer, Marker, Polyline, 
  Polygon, Circle, Popup, useMapEvents 
} from 'react-leaflet';
import L from 'leaflet';
import { Track, EWNode, TacticalZone, TacticalSensor } from '../types';
import { Navigation, Move, Edit3, Trash2 } from 'lucide-react';
import { EditableObject } from './TacticalObjectModal';

function getBeamSector(lat: number, lon: number, azimuth: number, beamwidth: number, rangeMeters: number): [number, number][] {
  const points: [number, number][] = [[lat, lon]];
  const halfBeam = beamwidth / 2;
  const startAngle = azimuth - halfBeam;
  const endAngle = azimuth + halfBeam;
  const step = 2;
  
  const mToLat = 1 / 111132.954;
  const mToLon = 1 / (111412.84 * Math.cos((lat * Math.PI) / 180));

  for (let a = startAngle; a <= endAngle; a += step) {
    const rad = (a * Math.PI) / 180;
    const pLat = lat + Math.cos(rad) * rangeMeters * mToLat;
    const pLon = lon + Math.sin(rad) * rangeMeters * mToLon;
    points.push([pLat, pLon]);
  }
  points.push([lat, lon]);
  return points;
}

function getPolygonCenter(coords: [number, number][]): [number, number] {
  if (!coords || coords.length === 0) return [0, 0];
  let latSum = 0;
  let lonSum = 0;
  for (const pt of coords) {
    latSum += pt[0];
    lonSum += pt[1];
  }
  return [latSum / coords.length, lonSum / coords.length];
}

const createCustomIcon = (svgContent: string, bg: string, border: string) => {
  return L.divIcon({
    className: 'custom-tactical-pin',
    html: `<div class="pin-inner" style="
      background: ${bg};
      border: 2px solid ${border};
      width: 32px;
      height: 32px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 10px ${border};
    ">${svgContent}</div>`,
    iconSize: [32, 32],
    iconAnchor: [16, 16]
  });
};

const icons = {
  drone: (heading: number) => L.divIcon({
    className: 'custom-drone-icon',
    html: `<div style="transform: rotate(${heading}deg); width: 26px; height: 26px; display: flex; align-items: center; justify-content: center;">
             <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5">
               <polygon points="12 2 19 21 12 17 5 21 12 2"></polygon>
             </svg>
           </div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13]
  }),
  ew: (isTransmitting: boolean) => createCustomIcon(
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${isTransmitting ? '#fff' : '#38bdf8'}" stroke-width="2"><path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/></svg>`,
    isTransmitting ? '#dc2626' : '#0f172a',
    isTransmitting ? '#f87171' : '#38bdf8'
  ),
  camera: () => createCustomIcon(
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2"><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/></svg>`,
    '#064e3b', '#34d399'
  ),
  acoustic: () => createCustomIcon(
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>`,
    '#451a03', '#fbbf24'
  ),
  observation_post: () => createCustomIcon(
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" stroke-width="2"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>`,
    '#2e1065', '#a78bfa'
  ),
  witness_report: () => createCustomIcon(
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f472b6" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" x2="19" y1="8" y2="14"/><line x1="22" x2="16" y1="11" y2="11"/></svg>`,
    '#701a75', '#f472b6'
  ),
  target_asset: () => createCustomIcon(
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,
    '#450a0a', '#ef4444'
  ),
  zone_anchor: (isSafe: boolean) => createCustomIcon(
    `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="${isSafe ? '#34d399' : '#f87171'}" stroke-width="3"><polyline points="5 9 2 12 5 15"/><polyline points="9 5 12 2 15 5"/><polyline points="15 19 12 22 9 19"/><polyline points="19 9 22 12 19 15"/><line x1="2" x2="22" y1="12" y2="12"/><line x1="12" x2="12" y1="2" y2="22"/></svg>`,
    isSafe ? '#064e3b' : '#450a0a',
    isSafe ? '#34d399' : '#f87171'
  )
};

const MapEventsController: React.FC<{ 
  onMapClick: (lat: number, lon: number) => void;
  onMouseMove: (lat: number, lon: number) => void;
}> = ({ onMapClick, onMouseMove }) => {
  useMapEvents({
    click(e) {
      onMapClick(e.latlng.lat, e.latlng.lng);
    },
    mousemove(e) {
      onMouseMove(e.latlng.lat, e.latlng.lng);
    }
  });
  return null;
};

// --- Окремий стабільний маркер РЕБ ---
const EWNodeMarkerItem: React.FC<{
  node: EWNode;
  onDragStart: (id: string) => void;
  onCommitMoveEW: (id: number, lat: number, lon: number) => void;
  onEditObject: (obj: EditableObject) => void;
  onDeleteEW: (id: number) => void;
}> = ({ node, onDragStart, onCommitMoveEW, onEditObject, onDeleteEW }) => {
  const memoPos = useMemo<[number, number]>(() => [node.lat, node.lon], [node.lat, node.lon]);
  const sector = useMemo(
    () => getBeamSector(node.lat, node.lon, node.azimuth, node.beamwidth, node.max_range),
    [node.lat, node.lon, node.azimuth, node.beamwidth, node.max_range]
  );

  const eventHandlers = useMemo(
    () => ({
      dragstart() {
        onDragStart(`ew-${node.id}`);
      },
      dragend(e: L.LeafletEvent) {
        const marker = e.target as L.Marker;
        const latlng = marker.getLatLng();
        onCommitMoveEW(node.id, latlng.lat, latlng.lng);
      }
    }),
    [node.id, onDragStart, onCommitMoveEW]
  );

  return (
    <>
      <Circle
        center={memoPos}
        radius={node.max_range}
        pathOptions={{
          color: node.is_transmitting ? '#ef4444' : '#38bdf8',
          fillColor: node.is_transmitting ? '#ef4444' : '#38bdf8',
          fillOpacity: 0.03,
          weight: 1,
          dashArray: '5, 8'
        }}
      />
      <Polygon
        positions={sector}
        pathOptions={{
          color: node.is_transmitting ? '#ef4444' : '#0284c7',
          weight: 1.5,
          fillColor: node.is_transmitting ? '#dc2626' : '#38bdf8',
          fillOpacity: node.is_transmitting ? 0.5 : 0.2
        }}
      />
      <Marker
        position={memoPos}
        icon={icons.ew(node.is_transmitting)}
        draggable={true}
        eventHandlers={eventHandlers}
      >
        <Popup>
          <div className="popup-tactical">
            <strong style={{ color: '#0284c7' }}>{node.name}</strong>
            <p style={{ margin: '3px 0' }}>Азимут: <b>{node.azimuth}°</b> (Кут {node.beamwidth}°)</p>
            <p style={{ margin: '3px 0' }}>Радіус: <b>{node.max_range} м</b></p>
            <p style={{ margin: '3px 0' }}>Статус: <b>{node.is_transmitting ? 'АКТИВНЕ ГЛУШІННЯ' : 'ГОТОВНІСТЬ'}</b></p>
            <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  onEditObject({ type: 'ew', data: node });
                }}
                className="btn-popup-edit"
              >
                <Edit3 size={12} /> Редагувати
              </button>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteEW(node.id);
                }}
                className="btn-popup-delete"
              >
                <Trash2 size={12} />
              </button>
            </div>
          </div>
        </Popup>
      </Marker>
    </>
  );
};

// --- Окремий стабільний маркер сенсора ---
const SensorMarkerItem: React.FC<{
  sensor: TacticalSensor;
  onDragStart: (id: string) => void;
  onCommitMoveSensor: (id: number, lat: number, lon: number) => void;
  onEditObject: (obj: EditableObject) => void;
  onDeleteSensor: (id: number) => void;
}> = ({ sensor, onDragStart, onCommitMoveSensor, onEditObject, onDeleteSensor }) => {
  const memoPos = useMemo<[number, number]>(() => [sensor.lat, sensor.lon], [sensor.lat, sensor.lon]);

  let icon = icons.camera();
  let circleColor = '#34d399';

  if (sensor.sensor_type === 'acoustic') {
    icon = icons.acoustic();
    circleColor = '#fbbf24';
  } else if (sensor.sensor_type === 'observation_post') {
    icon = icons.observation_post();
    circleColor = '#a78bfa';
  } else if (sensor.sensor_type === 'witness_report') {
    icon = icons.witness_report();
    circleColor = '#f472b6';
  } else if (sensor.sensor_type === 'target_asset') {
    icon = icons.target_asset();
    circleColor = '#f87171';
  }

  const eventHandlers = useMemo(
    () => ({
      dragstart() {
        onDragStart(`sensor-${sensor.id}`);
      },
      dragend(e: L.LeafletEvent) {
        const marker = e.target as L.Marker;
        const latlng = marker.getLatLng();
        onCommitMoveSensor(sensor.id, latlng.lat, latlng.lng);
      }
    }),
    [sensor.id, onDragStart, onCommitMoveSensor]
  );

  return (
    <>
      <Circle
        center={memoPos}
        radius={sensor.detection_radius}
        pathOptions={{
          color: circleColor,
          fillColor: circleColor,
          fillOpacity: 0.08,
          weight: 1,
          dashArray: '3, 6'
        }}
      />
      <Marker 
        position={memoPos} 
        icon={icon}
        draggable={true}
        eventHandlers={eventHandlers}
      >
        <Popup>
          <div className="popup-tactical">
            <strong>{sensor.name}</strong>
            <p style={{ margin: '3px 0' }}>Тип: <i>{sensor.sensor_type}</i></p>
            <p style={{ margin: '3px 0' }}>Радіус: <b>{sensor.detection_radius} м</b></p>
            {sensor.description && <p style={{ margin: '3px 0', color: '#475569' }}>{sensor.description}</p>}
            <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  onEditObject({ type: 'sensor', data: sensor });
                }}
                className="btn-popup-edit"
              >
                <Edit3 size={12} /> Редагувати
              </button>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteSensor(sensor.id);
                }}
                className="btn-popup-delete"
              >
                <Trash2 size={12} />
              </button>
            </div>
          </div>
        </Popup>
      </Marker>
    </>
  );
};

// --- Окремий стабільний маркер тактичної зони ---
const ZoneItem: React.FC<{
  zone: TacticalZone;
  onDragStart: (id: string) => void;
  onCommitMoveZone: (id: number, coords: [number, number][]) => void;
  onEditObject: (obj: EditableObject) => void;
  onDeleteZone: (id: number) => void;
}> = ({ zone, onDragStart, onCommitMoveZone, onEditObject, onDeleteZone }) => {
  const isSafe = zone.zone_type === 'safe';
  const center = useMemo(() => getPolygonCenter(zone.coordinates), [zone.coordinates]);
  const zoneDragRef = useRef<{ initCenter: [number, number]; initCoords: [number, number][] } | null>(null);

  const eventHandlers = useMemo(
    () => ({
      dragstart() {
        onDragStart(`zone-${zone.id}`);
        zoneDragRef.current = {
          initCenter: center,
          initCoords: zone.coordinates
        };
      },
      dragend(e: L.LeafletEvent) {
        if (!zoneDragRef.current) return;
        const marker = e.target as L.Marker;
        const cur = marker.getLatLng();
        const dLat = cur.lat - zoneDragRef.current.initCenter[0];
        const dLon = cur.lng - zoneDragRef.current.initCenter[1];
        const finalCoords = zoneDragRef.current.initCoords.map(([pLat, pLon]) => [
          pLat + dLat,
          pLon + dLon
        ]) as [number, number][];
        zoneDragRef.current = null;
        onCommitMoveZone(zone.id, finalCoords);
      }
    }),
    [zone.id, zone.coordinates, center, onDragStart, onCommitMoveZone]
  );

  return (
    <>
      <Polygon
        positions={zone.coordinates}
        pathOptions={{
          color: isSafe ? '#10b981' : '#ef4444',
          fillColor: isSafe ? '#059669' : '#b91c1c',
          fillOpacity: 0.25,
          weight: 2,
          dashArray: isSafe ? '4, 4' : undefined
        }}
      />
      <Marker
        position={center}
        icon={icons.zone_anchor(isSafe)}
        draggable={true}
        eventHandlers={eventHandlers}
      >
        <Popup>
          <div className="popup-tactical">
            <strong style={{ color: isSafe ? '#059669' : '#b91c1c' }}>
              {isSafe ? 'ЗЕЛЕНА ЗОНА (KILLBOX)' : 'ЧЕРВОНА ЗОНА (NO-DROP)'}
            </strong>
            <p style={{ margin: '4px 0', fontWeight: 'bold' }}>{zone.name}</p>
            <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  onEditObject({ type: 'zone', data: zone });
                }}
                className="btn-popup-edit"
              >
                <Edit3 size={12} /> Редагувати
              </button>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteZone(zone.id);
                }}
                className="btn-popup-delete"
              >
                <Trash2 size={12} />
              </button>
            </div>
          </div>
        </Popup>
      </Marker>
    </>
  );
};

interface Props {
  tracks: Track[];
  ewNodes: EWNode[];
  zones: TacticalZone[];
  sensors: TacticalSensor[];
  onMapClick: (lat: number, lon: number) => void;
  onDeleteZone: (id: number) => void;
  onDeleteSensor: (id: number) => void;
  onDeleteEW: (id: number) => void;
  onEditObject: (obj: EditableObject) => void;
  onDragStart: (id: string) => void;
  onCommitMoveEW: (id: number, lat: number, lon: number) => void;
  onCommitMoveSensor: (id: number, lat: number, lon: number) => void;
  onCommitMoveZone: (id: number, coords: [number, number][]) => void;
}

export const TacticalMap: React.FC<Props> = ({ 
  tracks, ewNodes, zones, sensors, 
  onMapClick, onDeleteZone, onDeleteSensor, onDeleteEW, onEditObject,
  onDragStart, onCommitMoveEW, onCommitMoveSensor, onCommitMoveZone
}) => {
  const defaultCenter: [number, number] = [50.4501, 30.5234];
  const [cursorCoords, setCursorCoords] = useState<{ lat: number; lon: number } | null>(null);

  const datumLat = 50.4501;
  const datumLon = 30.5234;
  const deltaX = cursorCoords ? ((cursorCoords.lon - datumLon) * 111412.84 * Math.cos((datumLat * Math.PI) / 180)).toFixed(0) : '0';
  const deltaY = cursorCoords ? ((cursorCoords.lat - datumLat) * 111132.954).toFixed(0) : '0';

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <MapContainer center={defaultCenter} zoom={11} style={{ width: '100%', height: '100%' }}>
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; CARTO'
        />

        <MapEventsController 
          onMapClick={onMapClick} 
          onMouseMove={(lat, lon) => setCursorCoords({ lat, lon })} 
        />

        {/* 1. ЗОНИ */}
        {zones.map((zone) => (
          <ZoneItem
            key={`zone-${zone.id}`}
            zone={zone}
            onDragStart={onDragStart}
            onCommitMoveZone={onCommitMoveZone}
            onEditObject={onEditObject}
            onDeleteZone={onDeleteZone}
          />
        ))}

        {/* 2. СЕНСОРИ */}
        {sensors.map((sensor) => (
          <SensorMarkerItem
            key={`sensor-${sensor.id}`}
            sensor={sensor}
            onDragStart={onDragStart}
            onCommitMoveSensor={onCommitMoveSensor}
            onEditObject={onEditObject}
            onDeleteSensor={onDeleteSensor}
          />
        ))}

        {/* 3. ВУЗЛИ РЕБ */}
        {ewNodes.map((node) => (
          <EWNodeMarkerItem
            key={`ew-${node.id}`}
            node={node}
            onDragStart={onDragStart}
            onCommitMoveEW={onCommitMoveEW}
            onEditObject={onEditObject}
            onDeleteEW={onDeleteEW}
          />
        ))}

        {/* 4. ТРЕКИ ЦІЛЕЙ */}
        {tracks.map((target) => (
          <React.Fragment key={`track-${target.id}`}>
            <Marker position={[target.lat, target.lon]} icon={icons.drone(target.heading)} />
            <Polyline
              positions={[[target.lat, target.lon], target.predicted_30s, target.predicted_60s]}
              pathOptions={{ color: '#fbbf24', dashArray: '4, 8', weight: 2 }}
            />
            <Circle
              center={target.crash_point}
              radius={200}
              pathOptions={{
                color: target.is_safe_to_engage ? '#10b981' : '#ef4444',
                fillColor: target.is_safe_to_engage ? '#10b981' : '#ef4444',
                fillOpacity: 0.35
              }}
            />
          </React.Fragment>
        ))}
      </MapContainer>

      {/* Координатний HUD */}
      <div className="cursor-coordinate-hud">
        <div className="hud-row">
          <Navigation size={14} color="#38bdf8" />
          <span className="hud-title">WGS-84:</span>
          {cursorCoords ? (
            <span className="hud-value">
              {cursorCoords.lat.toFixed(5)}° N, {cursorCoords.lon.toFixed(5)}° E
            </span>
          ) : (
            <span className="hud-value hud-dimmed">НАВЕДІТЬ НА КАРТУ</span>
          )}
        </div>
        {cursorCoords && (
          <div className="hud-row">
            <Move size={14} color="#34d399" />
            <span className="hud-title">LOCAL ENU:</span>
            <span className="hud-value">
              X: {deltaX >= '0' ? `+${deltaX}` : deltaX}m | Y: {deltaY >= '0' ? `+${deltaY}` : deltaY}m
            </span>
          </div>
        )}
      </div>
    </div>
  );
};