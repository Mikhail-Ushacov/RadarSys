// frontend/src/App.tsx
import React, { useState, useEffect, useRef } from 'react';
import { TacticalMap } from './components/TacticalMap';
import { TargetHUD } from './components/TargetHUD';
import { TacticalObjectModal, EditableObject } from './components/TacticalObjectModal';
import { InterceptionHistoryPage } from './components/InterceptionHistoryPage';
import { 
  TacticalUpdate, 
  Track, 
  EWNode, 
  TacticalZone, 
  TacticalSensor, 
  DownedDroneDetailed, 
  Emergency112Alert 
} from './types';
import { Map as MapIcon, History as HistoryIcon, Sun, Moon } from 'lucide-react';
import { Badge } from './components/ui';
import s from './App.module.css';
import { useTheme } from './theme';

export const App: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<'map' | 'history'>('map');
  const [tracks, setTracks] = useState<Track[]>([]);
  const [ewNodes, setEwNodes] = useState<EWNode[]>([]);
  const [zones, setZones] = useState<TacticalZone[]>([]);
  const [sensors, setSensors] = useState<TacticalSensor[]>([]);
  const [recentDowned, setRecentDowned] = useState<DownedDroneDetailed[]>([]);
  const [totalDownedCount, setTotalDownedCount] = useState<number>(0);

  const [simulationActive, setSimulationActive] = useState<boolean>(true);
  const [autoTracking, setAutoTracking] = useState<boolean>(true);
  const [emergencyOverride, setEmergencyOverride] = useState<boolean>(false);
  const [threatInfo, setThreatInfo] = useState<string | null>(null);
  const [emergency112Alert, setEmergency112Alert] = useState<Emergency112Alert | null>(null);

  const [allowMapClickToAdd, setAllowMapClickToAdd] = useState<boolean>(false);
  const [isDrawingZone, setIsDrawingZone] = useState<boolean>(false);
  const [drawingPoints, setDrawingPoints] = useState<[number, number][]>([]);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingObject, setEditingObject] = useState<EditableObject | null>(null);
  const [selectedCoords, setSelectedCoords] = useState<{ lat: number; lon: number }>({
    lat: 50.4501,
    lon: 30.5234
  });

  const draggingIdRef = useRef<string | null>(null);
  const { dark, toggle } = useTheme();
  const lastDragTimeRef = useRef<number>(0);
  const recentlyMovedRef = useRef<Map<string, number>>(new Map());

  const backendUrl = `http://${window.location.hostname}:8000`;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 0;
    let timer: number | undefined;

    const connect = () => {
      if (closed) return;
      ws = new WebSocket(`ws://${window.location.hostname}:8000/ws/tactical`);

      ws.onmessage = (event) => {
        retry = 0;
        let data: TacticalUpdate;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        setTracks(data.tracks || []);
        if (data.simulation_active !== undefined) setSimulationActive(data.simulation_active);
        if (data.auto_tracking !== undefined) setAutoTracking(data.auto_tracking);
        if (data.emergency_override !== undefined) setEmergencyOverride(data.emergency_override);
        setThreatInfo(data.threat_info || null);
        if (data.recent_downed) setRecentDowned(data.recent_downed);
        if (data.total_downed_count !== undefined) setTotalDownedCount(data.total_downed_count);
        if (data.emergency_112_alert !== undefined) setEmergency112Alert(data.emergency_112_alert);

        const now = Date.now();

        setEwNodes((prev) => {
          return (data.ew_nodes || []).map((node) => {
            const key = `ew-${node.id}`;
            if (draggingIdRef.current === key || (recentlyMovedRef.current.get(key) || 0) > now) {
              const current = prev.find((n) => n.id === node.id);
              return current ? { ...node, lat: current.lat, lon: current.lon } : node;
            }
            return node;
          });
        });

        setSensors((prev) => {
          return (data.sensors || []).map((sensor) => {
            const key = `sensor-${sensor.id}`;
            if (draggingIdRef.current === key || (recentlyMovedRef.current.get(key) || 0) > now) {
              const current = prev.find((s) => s.id === sensor.id);
              return current ? { ...sensor, lat: current.lat, lon: current.lon } : sensor;
            }
            return sensor;
          });
        });

        setZones((prev) => {
          return (data.zones || []).map((zone) => {
            const key = `zone-${zone.id}`;
            if (draggingIdRef.current === key || (recentlyMovedRef.current.get(key) || 0) > now) {
              const current = prev.find((z) => z.id === zone.id);
              return current ? { ...zone, coordinates: current.coordinates } : zone;
            }
            return zone;
          });
        });
      };

      ws.onclose = () => {
        if (closed) return;
        retry += 1;
        const backoff = Math.min(10000, 500 * 2 ** Math.min(retry, 5));
        timer = window.setTimeout(connect, backoff);
      };
      ws.onerror = () => {
        try { ws?.close(); } catch { /* ignore */ }
      };
    };

    connect();
    return () => {
      closed = true;
      if (timer !== undefined) window.clearTimeout(timer);
      try { ws?.close(); } catch { /* ignore */ }
    };
  }, []);

  const handleToggleSimulation = async () => {
    await fetch(`${backendUrl}/api/v1/simulation/toggle`, { method: 'POST' });
  };

  const handleToggleAutoTracking = async () => {
    await fetch(`${backendUrl}/api/v1/ew/toggle_autotracking`, { method: 'POST' });
  };

  const handleResetSimulation = async () => {
    await fetch(`${backendUrl}/api/v1/simulation/reset`, { method: 'POST' });
  };

  const handleTriggerBurst = async (nodeId: number) => {
    await fetch(`${backendUrl}/api/v1/ew/arm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: nodeId, arm: true, burst_duration: 20 })
    });
  };

  const handleMapClick = (lat: number, lon: number) => {
    if (isDrawingZone) return;
    if (!allowMapClickToAdd) return;
    if (Date.now() - lastDragTimeRef.current < 450) return;

    setEditingObject(null);
    setSelectedCoords({ lat, lon });
    setIsModalOpen(true);
  };

  const handleAddDrawingPoint = (lat: number, lon: number) => {
    setDrawingPoints((prev) => [...prev, [lat, lon]]);
  };

  const handleStartDrawingZone = () => {
    setIsDrawingZone(true);
    setDrawingPoints([]);
  };

  const handleFinishDrawingZone = () => {
    if (drawingPoints.length < 3) return;
    const centerLat = drawingPoints.reduce((acc, p) => acc + p[0], 0) / drawingPoints.length;
    const centerLon = drawingPoints.reduce((acc, p) => acc + p[1], 0) / drawingPoints.length;
    setSelectedCoords({ lat: centerLat, lon: centerLon });
    setEditingObject(null);
    setIsModalOpen(true);
    setIsDrawingZone(false);
  };

  const handleCancelDrawingZone = () => {
    setIsDrawingZone(false);
    setDrawingPoints([]);
  };

  const handleUndoDrawingPoint = () => {
    setDrawingPoints((prev) => prev.slice(0, -1));
  };

  const handleOpenAddModal = () => {
    setEditingObject(null);
    setIsModalOpen(true);
  };

  const handleEditObject = (obj: EditableObject) => {
    setEditingObject(obj);
    setIsModalOpen(true);
  };

  const handleDeleteZone = async (id: number) => {
    setZones((prev) => prev.filter((z) => z.id !== id));
    await fetch(`${backendUrl}/api/v1/zones/${id}`, { method: 'DELETE' });
  };

  const handleDeleteSensor = async (id: number) => {
    setSensors((prev) => prev.filter((s) => s.id !== id));
    await fetch(`${backendUrl}/api/v1/sensors/${id}`, { method: 'DELETE' });
  };

  const handleDeleteEW = async (id: number) => {
    setEwNodes((prev) => prev.filter((n) => n.id !== id));
    await fetch(`${backendUrl}/api/v1/ew/node/${id}`, { method: 'DELETE' });
  };

  const handleDragStart = (uniqueId: string) => {
    draggingIdRef.current = uniqueId;
  };

  const handleCommitMoveEW = async (id: number, lat: number, lon: number) => {
    lastDragTimeRef.current = Date.now();
    recentlyMovedRef.current.set(`ew-${id}`, Date.now() + 2500);
    draggingIdRef.current = null;

    setEwNodes((prev) => prev.map((n) => (n.id === id ? { ...n, lat, lon } : n)));

    await fetch(`${backendUrl}/api/v1/ew/node/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon })
    });
  };

  const handleCommitMoveSensor = async (id: number, lat: number, lon: number) => {
    lastDragTimeRef.current = Date.now();
    recentlyMovedRef.current.set(`sensor-${id}`, Date.now() + 2500);
    draggingIdRef.current = null;

    setSensors((prev) => prev.map((s) => (s.id === id ? { ...s, lat, lon } : s)));

    await fetch(`${backendUrl}/api/v1/sensors/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon })
    });
  };

  const handleCommitMoveZone = async (id: number, coordinates: [number, number][]) => {
    lastDragTimeRef.current = Date.now();
    recentlyMovedRef.current.set(`zone-${id}`, Date.now() + 2500);
    draggingIdRef.current = null;

    setZones((prev) => prev.map((z) => (z.id === id ? { ...z, coordinates } : z)));

    await fetch(`${backendUrl}/api/v1/zones/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ coordinates })
    });
  };

  return (
    <div className={s.root}>
      <header className={s.bar}>
        <div className={s.brand}>
          <span className={s.logo}>SURGICAL EW C2</span>
          <span className={s.divider}>|</span>
          <span className={s.sub}>СИСТЕМА ХІРУРГІЧНОГО ПРИДУШЕННЯ БПЛА ТА УПРАВЛІННЯ ЗОНАМИ</span>
        </div>
        <div className={s.tabs}>
          <button
            className={`${s.tab} ${currentPage === 'map' ? s.active : ''}`}
            onClick={() => setCurrentPage('map')}
          >
            <MapIcon size={15} /> ТАКТИЧНА КАРТА
          </button>
          <button
            className={`${s.tab} ${currentPage === 'history' ? s.active : ''}`}
            onClick={() => setCurrentPage('history')}
          >
            <HistoryIcon size={15} /> ЖУРНАЛ ЗБИТТІВ
            <Badge tone="info">{totalDownedCount}</Badge>
          </button>
          <button
            className={s.tab}
            onClick={toggle}
            aria-label="theme"
          >
            {dark ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </div>
      </header>

      {currentPage === 'history' ? (
        <InterceptionHistoryPage onBackToMap={() => setCurrentPage('map')} />
      ) : (
        <div className={s.body}>
          <TargetHUD 
            tracks={tracks} 
            ewNodes={ewNodes} 
            sensors={sensors}
            zones={zones}
            recentDowned={recentDowned}
            totalDownedCount={totalDownedCount}
            allowMapClickToAdd={allowMapClickToAdd}
            isDrawingZone={isDrawingZone}
            simulationActive={simulationActive}
            autoTracking={autoTracking}
            emergencyOverride={emergencyOverride}
            threatInfo={threatInfo}
            onToggleMapClickToAdd={() => setAllowMapClickToAdd((prev) => !prev)}
            onStartDrawingZone={handleStartDrawingZone}
            onToggleSimulation={handleToggleSimulation}
            onToggleAutoTracking={handleToggleAutoTracking}
            onResetSimulation={handleResetSimulation}
            onTriggerBurst={handleTriggerBurst} 
            onOpenAddModal={handleOpenAddModal}
            onEditObject={handleEditObject}
            onOpenHistoryPage={() => setCurrentPage('history')}
          />
          <div className={s.mapPane}>
            <TacticalMap 
              dark={dark}
              tracks={tracks} 
              ewNodes={ewNodes} 
              zones={zones}
              sensors={sensors}
              recentDowned={recentDowned}
              isDrawingZone={isDrawingZone}
              drawingPoints={drawingPoints}
              onAddDrawingPoint={handleAddDrawingPoint}
              onFinishDrawingZone={handleFinishDrawingZone}
              onCancelDrawingZone={handleCancelDrawingZone}
              onUndoDrawingPoint={handleUndoDrawingPoint}
              onMapClick={handleMapClick}
              onDeleteZone={handleDeleteZone}
              onDeleteSensor={handleDeleteSensor}
              onDeleteEW={handleDeleteEW}
              onEditObject={handleEditObject}
              onDragStart={handleDragStart}
              onCommitMoveEW={handleCommitMoveEW}
              onCommitMoveSensor={handleCommitMoveSensor}
              onCommitMoveZone={handleCommitMoveZone}
              emergency112Alert={emergency112Alert}
            />
          </div>

          {isModalOpen && (
            <TacticalObjectModal
              initialLat={selectedCoords.lat}
              initialLon={selectedCoords.lon}
              initialCoordinates={drawingPoints.length >= 3 ? drawingPoints : undefined}
              editingObject={editingObject}
              onClose={() => {
                setIsModalOpen(false);
                setEditingObject(null);
                setDrawingPoints([]);
              }}
              onSuccess={() => {
                setIsModalOpen(false);
                setEditingObject(null);
                setDrawingPoints([]);
              }}
            />
          )}
        </div>
      )}
    </div>
  );
};

export default App;