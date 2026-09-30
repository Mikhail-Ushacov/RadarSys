// frontend/src/components/TacticalMap.tsx
import React, { useState, useRef, useMemo, useEffect } from 'react';
import { 
  MapContainer, TileLayer, Marker, Polyline, 
  Polygon, Circle, Popup, useMapEvents 
} from 'react-leaflet';
import L from 'leaflet';
import { Track, EWNode, TacticalZone, TacticalSensor, DownedDroneDetailed, Emergency112Alert } from '../types';
import { Navigation, Move, Edit3, Trash2, CheckCircle2, RotateCcw, X, Siren } from 'lucide-react';
import { EditableObject } from './TacticalObjectModal';
import { Button } from './ui';
import m from './TacticalMap.module.css';

interface RiskCell { 
  cell: string; 
  safety: number; 
  risk: number; 
  b: number; 
  r: number; 
  poi?: number; 
  green?: number; 
  why: string; 
  boundary: [number, number][]; 
}

function safetyColor(s: number): string {
  if (s >= 60) return '#10b981';
  if (s >= 40) return '#f59e0b';
  return '#ef4444';
}

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

const vertexPointIcon = L.divIcon({
  className: 'custom-vertex-dot',
  html: `<div style="width: 12px; height: 12px; background: #38bdf8; border: 2px solid #ffffff; border-radius: 50%; box-shadow: 0 0 6px #0284c7;"></div>`,
  iconSize: [12, 12],
  iconAnchor: [6, 6]
});

const icons = {
  drone: (heading: number, status?: string) => {
    if (status === 'CRASHED') {
      return L.divIcon({
        className: 'custom-drone-crashed',
        html: `<div style="width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; background: #991b1b; border: 2.5px solid #f87171; border-radius: 50%; box-shadow: 0 0 18px #ef4444;">
                 <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.8">
                   <line x1="18" y1="6" x2="6" y2="18"></line>
                   <line x1="6" y1="6" x2="18" y2="18"></line>
                 </svg>
               </div>`,
        iconSize: [36, 36],
        iconAnchor: [18, 18]
      });
    }

    const isJammed = status === 'JAMMED';
    return L.divIcon({
      className: isJammed ? 'custom-drone-jammed' : 'custom-drone-icon',
      html: `<div style="transform: rotate(${heading}deg); width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; ${isJammed ? 'filter: drop-shadow(0 0 10px #f59e0b);' : ''}">
               <svg width="32" height="32" viewBox="0 0 24 24" fill="${isJammed ? '#f59e0b' : '#ef4444'}" stroke="#ffffff" stroke-width="1.8">
                 <polygon points="12 2 19 21 12 17 5 21 12 2"></polygon>
               </svg>
             </div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 17]
    });
  },
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
  target_asset: () => createCustomIcon(
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,
    '#450a0a', '#ef4444'
  ),
  rf_24ghz: () => createCustomIcon(
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fdba74" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19.07 4.93A10 10 0 0 0 6.99 3.34"/><path d="M4 6h.01"/><path d="M2.29 9.62A10 10 0 1 0 21.31 8.35"/><path d="M16.24 7.76A6 6 0 1 0 8.23 16.67"/><path d="M12 18h.01"/><path d="M17.99 11.66A6 6 0 0 1 15.77 16.67"/><circle cx="12" cy="12" r="2"/><path d="m13.41 10.59 5.66-5.66"/></svg>`,
    '#431407', '#fb923c'
  ),
  droneUnknown: () => L.divIcon({
    className: 'custom-drone-unknown',
    html: `<div style="
      width: 34px; 
      height: 34px; 
      display: flex; 
      align-items: center; 
      justify-content: center; 
      background: #b91c1c; 
      border: 2px dashed #ffffff; 
      border-radius: 50%; 
      color: #fff; 
      font-weight: 900; 
      font-size: 18px;
      box-shadow: 0 0 16px #ef4444;
      animation: pulse 1.2s infinite;
    ">?</div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17]
  }),
  zone_anchor: (zoneType: string) => {
    let border = '#f87171';
    if (zoneType === 'safe') border = '#34d399';
    else if (zoneType === 'caution') border = '#f59e0b';
    
    return L.divIcon({
      className: 'custom-zone-dot',
      html: `<div style="
        width: 10px;
        height: 10px;
        background: ${border};
        border: 1.5px solid #ffffff;
        border-radius: 50%;
        box-shadow: 0 0 6px ${border};
        opacity: 0.7;
      "></div>`,
      iconSize: [10, 10],
      iconAnchor: [5, 5]
    });
  }
};

const MapEventsController: React.FC<{ 
  onMapClick: (lat: number, lon: number) => void;
  onMouseMove: (lat: number, lon: number) => void;
}> = ({ onMapClick, onMouseMove }) => {
  useMapEvents({
    click(e) { onMapClick(e.latlng.lat, e.latlng.lng); },
    mousemove(e) { onMouseMove(e.latlng.lat, e.latlng.lng); }
  });
  return null;
};

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
      dragstart() { onDragStart(`ew-${node.id}`); },
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
          fillOpacity: node.is_transmitting ? 0.65 : 0.22
        }}
      />
      {node.target_lead_coord && (
        <Polyline 
          positions={[memoPos, node.target_lead_coord]}
          pathOptions={{ color: node.is_transmitting ? '#ef4444' : '#38bdf8', weight: 2, dashArray: '4, 4' }}
        />
      )}
      <Marker position={memoPos} icon={icons.ew(node.is_transmitting)} draggable={true} eventHandlers={eventHandlers}>
        <Popup>
          <div className={m.popup}>
            <strong className={m.toneInfo}>{node.name}</strong>
            <p>Наведення: <b>{node.azimuth}°</b></p>
            <p>Промінь: <b>{node.beamwidth}°</b> | Дальність: <b>{node.max_range}м</b></p>
            <p>Статус: <b>{node.is_transmitting ? 'АКТИВНЕ ПРИДУШЕННЯ' : 'АВТОСУПРОВІД'}</b></p>
            <div className={m.popupActions}>
              <Button variant="default" onClick={() => onEditObject({ type: 'ew', data: node })}>
                <Edit3 size={12} /> Редагувати
              </Button>
              <Button variant="danger" onClick={() => onDeleteEW(node.id)}>
                <Trash2 size={12} />
              </Button>
            </div>
          </div>
        </Popup>
      </Marker>
    </>
  );
};

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
  } else if (sensor.sensor_type === 'rf_24ghz') {
    icon = icons.rf_24ghz();
    circleColor = '#38bdf8';
  } else if (sensor.sensor_type === 'observation_post') {
    icon = icons.observation_post();
    circleColor = sensor.detection_radius > 2000 ? '#a855f7' : '#c084fc';
  } else if (sensor.sensor_type === 'target_asset') {
    icon = icons.target_asset();
    circleColor = '#ef4444';
  }

  const eventHandlers = useMemo(
    () => ({
      dragstart() { onDragStart(`sensor-${sensor.id}`); },
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
        pathOptions={{ color: circleColor, fillColor: circleColor, fillOpacity: 0.08, weight: 1, dashArray: '3, 6' }} 
      />
      <Marker position={memoPos} icon={icon} draggable={true} eventHandlers={eventHandlers}>
        <Popup>
          <div className={m.popup}>
            <strong>{sensor.name}</strong>
            <p>Тип: <i>{sensor.sensor_type}</i></p>
            <p>Радіус: <b>{sensor.detection_radius} м</b></p>
            {sensor.description && <p className={m.toneDim}>{sensor.description}</p>}
            <div className={m.popupActions}>
              <Button variant="default" onClick={() => onEditObject({ type: 'sensor', data: sensor })}>
                <Edit3 size={12} /> Редагувати
              </Button>
              <Button variant="danger" onClick={() => onDeleteSensor(sensor.id)}>
                <Trash2 size={12} />
              </Button>
            </div>
          </div>
        </Popup>
      </Marker>
    </>
  );
};

const ZoneItem: React.FC<{
  zone: TacticalZone;
  onDragStart: (id: string) => void;
  onCommitMoveZone: (id: number, coords: [number, number][]) => void;
  onEditObject: (obj: EditableObject) => void;
  onDeleteZone: (id: number) => void;
}> = ({ zone, onDragStart, onCommitMoveZone, onEditObject, onDeleteZone }) => {
  const center = useMemo(() => getPolygonCenter(zone.coordinates), [zone.coordinates]);
  const zoneDragRef = useRef<{ initCenter: [number, number]; initCoords: [number, number][] } | null>(null);

  let strokeColor = '#ef4444';
  let fillColor = '#b91c1c';
  let title = 'ЧЕРВОНА ЗОНА (ЗАБОРОНЕНО)';
  if (zone.zone_type === 'safe') {
    strokeColor = '#10b981';
    fillColor = '#059669';
    title = 'ЗЕЛЕНА ЗОНА (KILLBOX)';
  } else if (zone.zone_type === 'caution') {
    strokeColor = '#f59e0b';
    fillColor = '#d97706';
    title = 'ПОМАРАНЧЕВА ЗОНА (БУФЕР)';
  }

  const eventHandlers = useMemo(
    () => ({
      dragstart() {
        onDragStart(`zone-${zone.id}`);
        zoneDragRef.current = { initCenter: center, initCoords: zone.coordinates };
      },
      dragend(e: L.LeafletEvent) {
        if (!zoneDragRef.current) return;
        const marker = e.target as L.Marker;
        const cur = marker.getLatLng();
        const dLat = cur.lat - zoneDragRef.current.initCenter[0];
        const dLon = cur.lng - zoneDragRef.current.initCenter[1];
        const finalCoords = zoneDragRef.current.initCoords.map(([pLat, pLon]) => [pLat + dLat, pLon + dLon]) as [number, number][];
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
          color: strokeColor,
          fillColor: fillColor,
          fillOpacity: 0.28,
          weight: 1.8,
          dashArray: zone.zone_type === 'safe' ? '4, 4' : zone.zone_type === 'caution' ? '6, 6' : undefined
        }}
      />
      <Marker position={center} icon={icons.zone_anchor(zone.zone_type)} draggable={true} eventHandlers={eventHandlers}>
        <Popup>
          <div className={m.popup}>
            <strong style={{ color: strokeColor }}>{title}</strong>
            <p><b>{zone.name}</b></p>
            <div className={m.popupActions}>
              <Button variant="default" onClick={() => onEditObject({ type: 'zone', data: zone })}>
                <Edit3 size={12} /> Редагувати
              </Button>
              <Button variant="danger" onClick={() => onDeleteZone(zone.id)}>
                <Trash2 size={12} />
              </Button>
            </div>
          </div>
        </Popup>
      </Marker>
    </>
  );
};

interface Props {
  dark: boolean;
  tracks: Track[];
  ewNodes: EWNode[];
  zones: TacticalZone[];
  sensors: TacticalSensor[];
  recentDowned?: DownedDroneDetailed[];
  emergency112Alert?: Emergency112Alert | null;
  isDrawingZone: boolean;
  drawingPoints: [number, number][];
  onAddDrawingPoint: (lat: number, lon: number) => void;
  onFinishDrawingZone: () => void;
  onCancelDrawingZone: () => void;
  onUndoDrawingPoint: () => void;
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

const MAP_KEY = (import.meta as any).env?.VITE_MAP_API_KEY || '';

export const TacticalMap: React.FC<Props> = ({
  dark, tracks, ewNodes, zones, sensors, recentDowned = [], emergency112Alert,
  isDrawingZone, drawingPoints, onAddDrawingPoint, onFinishDrawingZone, onCancelDrawingZone, onUndoDrawingPoint,
  onMapClick, onDeleteZone, onDeleteSensor, onDeleteEW, onEditObject,
  onDragStart, onCommitMoveEW, onCommitMoveSensor, onCommitMoveZone
}) => {
  const defaultCenter: [number, number] = [50.4501, 30.5234];
  const [cursorCoords, setCursorCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [riskCells, setRiskCells] = useState<RiskCell[]>([]);
  const [showRisk, setShowRisk] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const url = `http://${window.location.hostname}:8000/api/v1/risk/grid?limit=35000`;
    fetch(url).then((r) => r.json()).then((d) => {
      if (!cancelled && d && Array.isArray(d.cells)) setRiskCells(d.cells);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const datumLat = 50.4501;
  const datumLon = 30.5234;
  const deltaX = cursorCoords ? ((cursorCoords.lon - datumLon) * 111412.84 * Math.cos((datumLat * Math.PI) / 180)).toFixed(0) : '0';
  const deltaY = cursorCoords ? ((cursorCoords.lat - datumLat) * 111132.954).toFixed(0) : '0';

  const handleContainerMapClick = (lat: number, lon: number) => {
    if (isDrawingZone) {
      onAddDrawingPoint(lat, lon);
    } else {
      onMapClick(lat, lon);
    }
  };

  return (
    <div className={m.wrap}>
      {/* ПОВІДОМЛЕННЯ ПРО ВИКЛИК 112 / ДСНС */}
      {emergency112Alert && emergency112Alert.called && (
        <div style={{
          position: 'absolute',
          top: 14,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 600,
          background: 'linear-gradient(135deg, #7f1d1d, #991b1b)',
          border: '2px solid #ef4444',
          borderRadius: 8,
          padding: '10px 16px',
          color: '#ffffff',
          boxShadow: '0 0 25px rgba(239, 68, 68, 0.6)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          maxWidth: 620
        }}>
          <Siren size={28} color="#fca5a5" />
          <div style={{ fontSize: '0.8rem', lineHeight: 1.35 }}>
            <strong style={{ display: 'block', color: '#fef08a', letterSpacing: '0.04em' }}>
              🚨 СЛУЖБА 112: ВИКЛИК АВАРІЙНИХ ПІДРОЗДІЛІВ ДСНС
            </strong>
            <span>{emergency112Alert.message}</span>
          </div>
        </div>
      )}

      {/* ПАНЕЛЬ МАЛЮВАННЯ ЗОНИ */}
      {isDrawingZone && (
        <div className={m.drawBar}>
          <div className={m.drawTitle}>
            <span>РЕЖИМ МАЛЮВАННЯ ЗОНИ ВІЛЬНОЇ ФОРМИ</span>
          </div>
          <div className={m.drawDesc}>
            Клікайте по карті, щоб позначити вершини контуру. Потрібно мінімум 3 точки.
          </div>
          <div className={m.drawActions}>
            <span className={m.drawCount}>ВЕРШИН: <b>{drawingPoints.length}</b></span>
            <Button
              variant="default"
              onClick={onUndoDrawingPoint}
              disabled={drawingPoints.length === 0}
              title="Видалити останню точку"
            >
              <RotateCcw size={14} /> Скасувати точку
            </Button>
            <Button
              variant="success"
              onClick={onFinishDrawingZone}
              disabled={drawingPoints.length < 3}
              title="Замкнути полігон та зберегти в БД"
            >
              <CheckCircle2 size={14} /> Завершити та зберегти
            </Button>
            <Button variant="danger" onClick={onCancelDrawingZone}>
              <X size={14} /> Скасувати
            </Button>
          </div>
        </div>
      )}

      <MapContainer center={defaultCenter} zoom={11} style={{ width: '100%', height: '100%' }}>
        <TileLayer 
          url={`https://tiles.stadiamaps.com/tiles/${dark ? 'alidade_smooth_dark' : 'alidade_smooth'}/{z}/{x}/{y}{r}.png?api_key=${MAP_KEY}`}
          attribution='&copy; Stadia Maps &copy; OpenStreetMap'
        />

        <MapEventsController 
          onMapClick={handleContainerMapClick} 
          onMouseMove={(lat, lon) => setCursorCoords({ lat, lon })} 
        />

        {showRisk && riskCells.map((c) => (
          <Polygon
            key={`risk-${c.cell}`}
            positions={c.boundary}
            pathOptions={{
              stroke: false,
              fillColor: safetyColor(c.safety),
              fillOpacity: 0.35,
            }}
          >
            <Popup>
              <div className={m.popup}>
                <strong>H3 Комірка · безпека <span style={{ color: safetyColor(c.safety) }}>{c.safety.toFixed(1)}%</span></strong>
                <p>{c.why}</p>
                <p className={m.toneDim}>Ризик: {c.risk.toFixed(0)}% | Будівель: {c.b} | Доріг: {c.r}</p>
              </div>
            </Popup>
          </Polygon>
        ))}

        {/* ТАКТИЧНІ РАЙОНИ */}
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

        {/* ПОПЕРЕДНІЙ ПЕРЕГЛЯД ЗОНИ ПРИ МАЛЮВАННІ */}
        {isDrawingZone && drawingPoints.length > 0 && (
          <>
            <Polyline 
              positions={drawingPoints.length > 2 ? [...drawingPoints, drawingPoints[0]] : drawingPoints} 
              pathOptions={{ color: '#38bdf8', weight: 2.5, dashArray: '5, 5' }} 
            />
            {drawingPoints.map((pt, idx) => (
              <Marker key={`draw-pt-${idx}`} position={pt} icon={vertexPointIcon} />
            ))}
          </>
        )}

        {/* СЕНСОРИ */}
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

        {/* КОМПЛЕКСИ РЕБ */}
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

        {/* ЗБЕРЕЖЕНІ МІСЦЯ ЗБИТТЯ ДРОНІВ ТА ЇХНІ ЧЕРВОНІ КОЛА РОЗЛЬОТУ УЛАМКІВ */}
        {recentDowned.map((d) => (
          <React.Fragment key={`downed-site-${d.id}`}>
            {/* ЯСКРАВЕ ЧЕРВОНЕ КОЛО РОЗЛЬОТУ УЛАМКІВ */}
            <Circle
              center={[d.crash_lat, d.crash_lon]}
              radius={d.debris_radius_m || 140}
              pathOptions={{
                color: d.emergency_112_called ? '#ef4444' : '#10b981',
                fillColor: d.emergency_112_called ? '#dc2626' : '#059669',
                fillOpacity: 0.28,
                weight: 2.5,
                dashArray: '5, 5'
              }}
            />
            {/* Епіцентр удару */}
            <Circle
              center={[d.crash_lat, d.crash_lon]}
              radius={20}
              pathOptions={{
                color: '#ffffff',
                fillColor: d.emergency_112_called ? '#b91c1c' : '#047857',
                fillOpacity: 0.8,
                weight: 2
              }}
            />
            <Marker position={[d.crash_lat, d.crash_lon]} icon={icons.drone(0, 'CRASHED')}>
              <Popup>
                <div className={m.popup}>
                  <strong className={m.toneDanger}>💥 МІСЦЕ ПАДІННЯ: {d.drone_id}</strong>
                  <p>Тип БПЛА: <b>{d.drone_type}</b></p>
                  <p>Час збиття: <b>{d.downed_time}</b></p>
                  <p>Комплекс РЕБ: <b>{d.interceptor_name}</b></p>
                  <p>Сектор: <b>{d.crash_zone}</b></p>
                  <p>Радіус розльоту уламків: <b className="t-mono" style={{ color: '#ef4444' }}>~{d.debris_radius_m || 120} м</b></p>
                  {d.emergency_112_called ? (
                    <p style={{ color: '#ef4444', fontWeight: 700, margin: '6px 0 0 0' }}>
                      🚨 Направлено рятувальні служби ДСНС / 112
                    </p>
                  ) : (
                    <p style={{ color: '#10b981', fontWeight: 600, margin: '4px 0 0 0' }}>
                      🟢 Падіння у Killbox (загрози людям немає)
                    </p>
                  )}
                </div>
              </Popup>
            </Marker>
          </React.Fragment>
        ))}

        {/* ПОВІТРЯНІ ЦІЛІ (АКТИВНИЙ ТРЕК) */}
        {tracks.map((target) => {
          const isInitialContact = target.detection_stage === 'INITIAL_CONTACT' || target.status === 'DETECTING';
          const isCrashed = target.status === 'CRASHED';

          return (
            <React.Fragment key={`track-${target.id}`}>
              {/* ЧЕРВОНЕ КОЛО РОЗЛЬОТУ УЛАМКІВ БІЛЯ АКТИВНОГО ЗБИТОГО ДРОНА */}
              {isCrashed && (
                <>
                  <Circle
                    center={[target.lat, target.lon]}
                    radius={target.debris_radius_m || 160}
                    pathOptions={{
                      color: '#ef4444',
                      fillColor: '#b91c1c',
                      fillOpacity: 0.35,
                      weight: 3,
                      dashArray: '6, 6'
                    }}
                  />
                  <Circle
                    center={[target.lat, target.lon]}
                    radius={22}
                    pathOptions={{
                      color: '#ffffff',
                      fillColor: '#dc2626',
                      fillOpacity: 0.85,
                      weight: 2
                    }}
                  />
                </>
              )}

              <Marker 
                position={[target.lat, target.lon]} 
                icon={isInitialContact ? icons.droneUnknown() : icons.drone(target.heading ?? 0, target.status)}
              >
                <Popup>
                  <div className={m.popup}>
                    <strong className={isInitialContact ? m.toneCaution : isCrashed ? m.toneDanger : m.toneInfo}>
                      {target.id} — {target.drone_type || 'БПЛА'} {isInitialContact ? '⚠️ (1-Й КОНТАКТ)' : (isCrashed ? '💥 (ЗБИТО)' : '🎯 (СУПРОВІД)')}
                    </strong>
                    <p>Джерело: <b>{target.last_sensor || 'Сенсор'}</b></p>
                    <p>Швидкість: <b>{target.speed !== null ? `${(target.speed * 3.6).toFixed(0)} км/год` : 'НЕ РОЗРАХОВАНО (?)'}</b></p>
                    <p>Курс: <b>{target.heading !== null ? `${target.heading.toFixed(0)}°` : 'НЕ РОЗРАХОВАНО (?)'}</b></p>
                    {isCrashed && (
                      <p>Розліт уламків: <b className="t-mono" style={{ color: '#ef4444' }}>~{target.debris_radius_m || 160} м</b></p>
                    )}
                    {isInitialContact && (
                      <p className={m.popupNote}>
                        Очікується 2-й контакт (камера/мікрофон/МВГ) для розрахунку вектора польоту
                      </p>
                    )}
                    {target.crash_safety !== null && target.crash_safety !== undefined && !isCrashed && (
                      <p>Безпека падіння: <b style={{ color: safetyColor(target.crash_safety) }}>{target.crash_safety.toFixed(1)}%</b></p>
                    )}
                  </div>
                </Popup>
              </Marker>

              {/* ПЛАВНА ПУНКТИРНА ЛІНІЯ НАПРЯМКУ РУХУ ДО ЦІЛІ */}
              {!isInitialContact && !isCrashed && target.predicted_30s && target.predicted_60s && (
                <>
                  <Polyline 
                    positions={[[target.lat, target.lon], target.predicted_30s, target.predicted_60s]} 
                    pathOptions={{ color: target.status === 'JAMMED' ? '#f59e0b' : '#38bdf8', dashArray: '5, 8', weight: 2.5 }} 
                  />
                  {target.impact_ellipse && target.impact_ellipse.length >= 3 && (
                    <Polygon
                      positions={target.impact_ellipse}
                      pathOptions={{
                        color: target.is_ci_critical ? '#dc2626' : (target.is_safe_to_engage ? '#10b981' : '#ef4444'),
                        fillColor: target.is_ci_critical ? '#dc2626' : (target.is_safe_to_engage ? '#10b981' : '#ef4444'),
                        fillOpacity: 0.32,
                        weight: target.is_ci_critical ? 3 : 1.5
                      }}
                    />
                  )}
                </>
              )}
            </React.Fragment>
          );
        })}
      </MapContainer>

      {/* КНОПКА ПЕРЕМИКАННЯ РЕЖИМІВ */}
      <div className={m.toggleBox}>
        <Button variant="default" onClick={() => setShowRisk((v) => !v)}>
          {showRisk ? 'Сховати H3 гексагони' : 'Показати сирі H3 гексагони'}
        </Button>
      </div>

      {/* ТАКТИЧНА ЛЕГЕНДА */}
      <div className={m.legend}>
        <div className={m.legendTitle}>ТАКТИЧНІ РАЙОНИ:</div>
        <div className={m.legendRow}>
          <span className={`${m.swatch} ${m.swSafe}`} />
          <b>Зелена зона (≥60%)</b> — Killbox, ураження дозволено
        </div>
        <div className={m.legendRow}>
          <span className={`${m.swatch} ${m.swCaution}`} />
          <b>Помаранчева зона (40-60%)</b> — Буфер, виклик 112 при падінні
        </div>
        <div className={m.legendRow}>
          <span className={`${m.swatch} ${m.swDanger}`} />
          <b>Червона зона (&lt;40%)</b> — Заборонено, аварійний виклик 112
        </div>
      </div>

      <div className={m.cursorHud}>
        <div className={m.hudRow}>
          <Navigation size={14} className={m.toneInfo} />
          <span className={m.hudTitle}>WGS-84:</span>
          {cursorCoords ? (
            <span className={m.hudValue}>{cursorCoords.lat.toFixed(5)}° N, {cursorCoords.lon.toFixed(5)}° E</span>
          ) : (
            <span className={`${m.hudValue} ${m.dimmed}`}>НАВЕДІТЬ НА КАРТУ</span>
          )}
        </div>
        {cursorCoords && (
          <div className={m.hudRow}>
            <Move size={14} className={m.toneSafe} />
            <span className={m.hudTitle}>LOCAL ENU:</span>
            <span className={m.hudValue}>X: {deltaX >= '0' ? `+${deltaX}` : deltaX}m | Y: {deltaY >= '0' ? `+${deltaY}` : deltaY}m</span>
          </div>
        )}
      </div>
    </div>
  );
};