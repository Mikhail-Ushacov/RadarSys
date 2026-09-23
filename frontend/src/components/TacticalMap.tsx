// frontend/src/components/TacticalMap.tsx
import React, { useState, useRef, useMemo, useEffect } from 'react';
import { 
  MapContainer, TileLayer, Marker, Polyline, 
  Polygon, Circle, Popup, useMapEvents 
} from 'react-leaflet';
import L from 'leaflet';
import { Track, EWNode, TacticalZone, TacticalSensor } from '../types';
import { Navigation, Move, Edit3, Trash2, CheckCircle2, RotateCcw, X } from 'lucide-react';
import { EditableObject } from './TacticalObjectModal';

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
  if (s >= 60) return '#10b981'; // Зелений
  if (s >= 40) return '#f59e0b'; // Помаранчевий
  return '#ef4444';              // Червоний
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
        html: `<div style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; background: #991b1b; border: 2px solid #f87171; border-radius: 50%; box-shadow: 0 0 15px #ef4444;">
                 <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5">
                   <line x1="18" y1="6" x2="6" y2="18"></line>
                   <line x1="6" y1="6" x2="18" y2="18"></line>
                 </svg>
               </div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16]
      });
    }

    const isJammed = status === 'JAMMED';
    return L.divIcon({
      className: isJammed ? 'custom-drone-jammed' : 'custom-drone-icon',
      html: `<div style="transform: rotate(${heading}deg); width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; ${isJammed ? 'filter: drop-shadow(0 0 8px #f59e0b);' : ''}">
               <svg width="30" height="30" viewBox="0 0 24 24" fill="${isJammed ? '#f59e0b' : '#ef4444'}" stroke="#ffffff" stroke-width="1.8">
                 <polygon points="12 2 19 21 12 17 5 21 12 2"></polygon>
               </svg>
             </div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16]
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
  witness_report: () => createCustomIcon(
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f472b6" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" x2="19" y1="8" y2="14"/><line x1="22" x2="16" y1="11" y2="11"/></svg>`,
    '#701a75', '#f472b6'
  ),
  target_asset: () => createCustomIcon(
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,
    '#450a0a', '#ef4444'
  ),
  zone_anchor: (zoneType: string) => {
    let bg = '#450a0a';
    let border = '#f87171';
    if (zoneType === 'safe') {
      bg = '#064e3b';
      border = '#34d399';
    } else if (zoneType === 'caution') {
      bg = '#451a03';
      border = '#f59e0b';
    }
    return createCustomIcon(
      `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="${border}" stroke-width="3"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
      bg, border
    );
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
          pathOptions={{
            color: node.is_transmitting ? '#ef4444' : '#38bdf8',
            weight: 2,
            dashArray: '4, 4'
          }}
        />
      )}
      <Marker position={memoPos} icon={icons.ew(node.is_transmitting)} draggable={true} eventHandlers={eventHandlers}>
        <Popup>
          <div className="popup-tactical">
            <strong style={{ color: '#0284c7' }}>{node.name}</strong>
            <p style={{ margin: '3px 0' }}>Наведення: <b>{node.azimuth}°</b></p>
            <p style={{ margin: '3px 0' }}>Промінь: <b>{node.beamwidth}°</b></p>
            <p style={{ margin: '3px 0' }}>Радіус: <b>{node.max_range} м</b></p>
            <p style={{ margin: '3px 0' }}>Статус: <b>{node.is_transmitting ? 'АКТИВНИЙ ВОГОНЬ (JAMMING)' : 'АВТОСУПРОВІД'}</b></p>
            <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
              <button onClick={(e) => { e.stopPropagation(); onEditObject({ type: 'ew', data: node }); }} className="btn-popup-edit">
                <Edit3 size={12} /> Редагувати
              </button>
              <button onClick={(e) => { e.stopPropagation(); onDeleteEW(node.id); }} className="btn-popup-delete">
                <Trash2 size={12} />
              </button>
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
      <Circle center={memoPos} radius={sensor.detection_radius} pathOptions={{ color: circleColor, fillColor: circleColor, fillOpacity: 0.08, weight: 1, dashArray: '3, 6' }} />
      <Marker position={memoPos} icon={icon} draggable={true} eventHandlers={eventHandlers}>
        <Popup>
          <div className="popup-tactical">
            <strong>{sensor.name}</strong>
            <p style={{ margin: '3px 0' }}>Тип: <i>{sensor.sensor_type}</i></p>
            <p style={{ margin: '3px 0' }}>Радіус: <b>{sensor.detection_radius} м</b></p>
            {sensor.description && <p style={{ margin: '3px 0', color: '#475569' }}>{sensor.description}</p>}
            <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
              <button onClick={(e) => { e.stopPropagation(); onEditObject({ type: 'sensor', data: sensor }); }} className="btn-popup-edit">
                <Edit3 size={12} /> Редагувати
              </button>
              <button onClick={(e) => { e.stopPropagation(); onDeleteSensor(sensor.id); }} className="btn-popup-delete">
                <Trash2 size={12} />
              </button>
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
          <div className="popup-tactical">
            <strong style={{ color: strokeColor }}>{title}</strong>
            <p style={{ margin: '4px 0', fontWeight: 'bold' }}>{zone.name}</p>
            <p style={{ margin: '2px 0', fontSize: '0.72rem', color: '#64748b' }}>Вершин контуру: {zone.coordinates.length}</p>
            <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
              <button onClick={(e) => { e.stopPropagation(); onEditObject({ type: 'zone', data: zone }); }} className="btn-popup-edit">
                <Edit3 size={12} /> Редагувати
              </button>
              <button onClick={(e) => { e.stopPropagation(); onDeleteZone(zone.id); }} className="btn-popup-delete">
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
  tracks, ewNodes, zones, sensors, 
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
    const url = `http://${window.location.hostname}:8000/api/v1/risk/grid?limit=3000`;
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
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      {/* ПАНЕЛЬ УПРАВЛІННЯ РЕЖИМОМ МАЛЮВАННЯ ЗОНИ ВІЛЬНОЇ ФОРМИ */}
      {isDrawingZone && (
        <div className="drawing-toolbar-overlay">
          <div className="drawing-toolbar-title">
            <span className="pulse-dot"></span> РЕЖИМ МАЛЮВАННЯ ЗОНИ ВІЛЬНОЇ ФОРМИ
          </div>
          <div className="drawing-toolbar-desc">
            Клікайте по карті, щоб позначити вершини контуру. Потрібно мінімум 3 точки.
          </div>
          <div className="drawing-toolbar-actions">
            <span className="drawing-points-count">ВЕРШИН: <b>{drawingPoints.length}</b></span>
            <button 
              onClick={onUndoDrawingPoint} 
              disabled={drawingPoints.length === 0} 
              className="btn-draw-tool"
              title="Видалити останню точку"
            >
              <RotateCcw size={14} /> Скасувати точку
            </button>
            <button 
              onClick={onFinishDrawingZone} 
              disabled={drawingPoints.length < 3} 
              className="btn-draw-tool finish"
              title="Замкнути полігон та зберегти в БД"
            >
              <CheckCircle2 size={14} /> Завершити та зберегти
            </button>
            <button onClick={onCancelDrawingZone} className="btn-draw-tool cancel">
              <X size={14} /> Скасувати
            </button>
          </div>
        </div>
      )}

      <MapContainer center={defaultCenter} zoom={11} style={{ width: '100%', height: '100%' }}>
        <TileLayer 
          url={`https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png?api_key=${MAP_KEY}`}
          attribution='&copy; Stadia Maps &copy; OpenStreetMap'
        />

        <MapEventsController 
          onMapClick={handleContainerMapClick} 
          onMouseMove={(lat, lon) => setCursorCoords({ lat, lon })} 
        />

        {/* ШАР ПЕРЕГЛЯДУ ГЕКСАГОНАЛЬНОЇ СІТКИ (ЯКЩО УВІМКНЕНО) */}
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
              <div className="popup-tactical">
                <strong>H3 Комірка · безпека <span style={{ color: safetyColor(c.safety) }}>{c.safety.toFixed(1)}%</span></strong>
                <p style={{ margin: '4px 0' }}>{c.why}</p>
                <p style={{ margin: '3px 0', color: '#475569' }}>Ризик: {c.risk.toFixed(0)}% | Будівель: {c.b} | Доріг: {c.r}</p>
              </div>
            </Popup>
          </Polygon>
        ))}

        {/* ТАКТИЧНІ РАЙОНИ ТА ЗОНИ ВІЛЬНОЇ ФОРМИ */}
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

        {/* ПЕРЕДПРОГЛЯД ПОЛІГОНУ, ЩО МАЛЮЄТЬСЯ В ЦЕЙ МОМЕНТ */}
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

        {tracks.map((target) => (
          <React.Fragment key={`track-${target.id}`}>
            <Marker position={[target.lat, target.lon]} icon={icons.drone(target.heading, target.status)}>
              <Popup>
                <div className="popup-tactical">
                  <strong style={{ color: target.status === 'CRASHED' ? '#ef4444' : target.status === 'JAMMED' ? '#f59e0b' : '#38bdf8' }}>
                    {target.id} {target.status === 'CRASHED' ? '💥 (ЗБИТО)' : target.status === 'JAMMED' ? '⚡ (ПРИДУШЕНО)' : '(В ПОЛЬОТІ)'}
                  </strong>
                  <p style={{ margin: '3px 0' }}>Висота: <b>{target.alt.toFixed(0)} м</b></p>
                  <p style={{ margin: '3px 0' }}>Швидкість: <b>{(target.speed * 3.6).toFixed(0)} км/год</b></p>
                  <p style={{ margin: '3px 0' }}>Курс: <b>{target.heading.toFixed(0)}°</b></p>
                  {target.crash_safety !== undefined && (
                    <p style={{ margin: '3px 0' }}>Безпека точки падіння: <b style={{ color: safetyColor(target.crash_safety) }}>{target.crash_safety.toFixed(1)}%</b></p>
                  )}
                  {target.nearest_ci && <p style={{ margin: '3px 0' }}>До {target.nearest_ci}: <b>{target.ci_distance} м</b></p>}
                </div>
              </Popup>
            </Marker>

            {target.status !== 'CRASHED' && (
              <>
                <Polyline positions={[[target.lat, target.lon], target.predicted_30s, target.predicted_60s]} pathOptions={{ color: target.status === 'JAMMED' ? '#f59e0b' : '#fbbf24', dashArray: '4, 8', weight: 2 }} />
                {target.impact_ellipse && target.impact_ellipse.length >= 3 ? (
                  <Polygon
                    positions={target.impact_ellipse}
                    pathOptions={{
                      color: target.is_ci_critical ? '#dc2626' : (target.is_safe_to_engage ? '#10b981' : '#ef4444'),
                      fillColor: target.is_ci_critical ? '#dc2626' : (target.is_safe_to_engage ? '#10b981' : '#ef4444'),
                      fillOpacity: 0.35,
                      weight: target.is_ci_critical ? 3 : 1.5
                    }}
                  />
                ) : (
                  <Circle
                    center={target.crash_point}
                    radius={220}
                    pathOptions={{
                      color: target.is_ci_critical ? '#dc2626' : (target.is_safe_to_engage ? '#10b981' : '#ef4444'),
                      fillColor: target.is_ci_critical ? '#dc2626' : (target.is_safe_to_engage ? '#10b981' : '#ef4444'),
                      fillOpacity: 0.45,
                      weight: target.is_ci_critical ? 3 : 1.5
                    }}
                  />
                )}
              </>
            )}
          </React.Fragment>
        ))}
      </MapContainer>

      {/* КНОПКА ПЕРЕМИКАННЯ РЕЖИМІВ */}
      <div style={{ position: 'absolute', top: 12, right: 12, zIndex: 500, display: 'flex', gap: 8, alignItems: 'center' }}>
        <button 
          onClick={() => setShowRisk((v) => !v)} 
          style={{ background: '#0f172a', color: '#e2e8f0', border: '1px solid #334155', borderRadius: 6, padding: '6px 10px', cursor: 'pointer', fontSize: 12 }}
        >
          {showRisk ? 'Сховати H3 гексагони' : 'Показати сирі H3 гексагони'}
        </button>
      </div>

      {/* ТАКТИЧНА ЛЕГЕНДА ЗОН БЕЗПЕКИ */}
      <div style={{ position: 'absolute', bottom: 20, left: 12, zIndex: 500, background: 'rgba(15,23,42,0.92)', border: '1px solid #334155', borderRadius: 6, padding: '8px 12px', fontSize: 11, color: '#e2e8f0' }}>
        <div style={{ fontWeight: 'bold', marginBottom: 4, letterSpacing: '0.04em' }}>ТАКТИЧНІ РАЙОНИ:</div>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 2 }}>
          <span style={{ display: 'inline-block', width: 12, height: 12, background: '#10b981', marginRight: 6, borderRadius: 2 }} />
          <b>Зелена зона (≥60%)</b> — Killbox, ураження дозволено
        </div>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 2 }}>
          <span style={{ display: 'inline-block', width: 12, height: 12, background: '#f59e0b', marginRight: 6, borderRadius: 2 }} />
          <b>Помаранчева зона (40-60%)</b> — Буфер, утриматись
        </div>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <span style={{ display: 'inline-block', width: 12, height: 12, background: '#ef4444', marginRight: 6, borderRadius: 2 }} />
          <b>Червона зона (&lt;40%)</b> — Місто/люди, падіння заборонено
        </div>
      </div>

      <div className="cursor-coordinate-hud">
        <div className="hud-row">
          <Navigation size={14} color="#38bdf8" />
          <span className="hud-title">WGS-84:</span>
          {cursorCoords ? (
            <span className="hud-value">{cursorCoords.lat.toFixed(5)}° N, {cursorCoords.lon.toFixed(5)}° E</span>
          ) : (
            <span className="hud-value hud-dimmed">НАВЕДІТЬ НА КАРТУ</span>
          )}
        </div>
        {cursorCoords && (
          <div className="hud-row">
            <Move size={14} color="#34d399" />
            <span className="hud-title">LOCAL ENU:</span>
            <span className="hud-value">X: {deltaX >= '0' ? `+${deltaX}` : deltaX}m | Y: {deltaY >= '0' ? `+${deltaY}` : deltaY}m</span>
          </div>
        )}
      </div>
    </div>
  );
};