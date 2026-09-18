// frontend/src/App.tsx
import React, { useState, useEffect, useRef } from 'react';
import { TacticalMap } from './components/TacticalMap';
import { TargetHUD } from './components/TargetHUD';
import { TacticalObjectModal, EditableObject } from './components/TacticalObjectModal';
import { TacticalUpdate, Track, EWNode, TacticalZone, TacticalSensor } from './types';

export const App: React.FC = () => {
  const [tracks, setTracks] = useState<Track[]>([]);
  const [ewNodes, setEwNodes] = useState<EWNode[]>([]);
  const [zones, setZones] = useState<TacticalZone[]>([]);
  const [sensors, setSensors] = useState<TacticalSensor[]>([]);
  
  // Режим створення нового об'єкта при кліку на карті (за замовчуванням увімкнено)
  const [allowMapClickToAdd, setAllowMapClickToAdd] = useState<boolean>(true);

  // Стан модального вікна та об'єкта для редагування
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingObject, setEditingObject] = useState<EditableObject | null>(null);
  const [selectedCoords, setSelectedCoords] = useState<{ lat: number; lon: number }>({
    lat: 50.4501,
    lon: 30.5234
  });

  // Захист від перезапису координат під час перетягування та 2.5 сек після нього
  const draggingIdRef = useRef<string | null>(null);
  const lastDragTimeRef = useRef<number>(0);
  const recentlyMovedRef = useRef<Map<string, number>>(new Map());

  const backendUrl = `http://${window.location.hostname}:8000`;

  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.hostname}:8000/ws/tactical`);

    ws.onmessage = (event) => {
      const data: TacticalUpdate = JSON.parse(event.data);
      setTracks(data.tracks || []);

      const now = Date.now();

      // Оновлюємо списки, блокуючи перетирання об'єктів, які перетягують або щойно перемістили
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

    return () => ws.close();
  }, []);

  const handleTriggerBurst = async (nodeId: number) => {
    await fetch(`${backendUrl}/api/v1/ew/arm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: nodeId, arm: true, burst_duration: 20 })
    });
  };

  const handleMapClick = (lat: number, lon: number) => {
    // Якщо створення по ЛКМ вимкнено або клік стався в момент відпускання маркера
    if (!allowMapClickToAdd) return;
    if (Date.now() - lastDragTimeRef.current < 450) return;

    setEditingObject(null);
    setSelectedCoords({ lat, lon });
    setIsModalOpen(true);
  };

  const handleOpenAddModal = () => {
    setEditingObject(null);
    setIsModalOpen(true);
  };

  const handleEditObject = (obj: EditableObject) => {
    setEditingObject(obj);
    setIsModalOpen(true);
  };

  // Видалення об'єктів
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

  // Drag & drop handlers
  const handleDragStart = (uniqueId: string) => {
    draggingIdRef.current = uniqueId;
  };

  const handleCommitMoveEW = async (id: number, lat: number, lon: number) => {
    lastDragTimeRef.current = Date.now();
    recentlyMovedRef.current.set(`ew-${id}`, Date.now() + 2500);
    draggingIdRef.current = null;

    // Оптимістичне оновлення локального стану
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
    <div className="tactical-container">
      <TargetHUD 
        tracks={tracks} 
        ewNodes={ewNodes} 
        sensors={sensors}
        zones={zones}
        allowMapClickToAdd={allowMapClickToAdd}
        onToggleMapClickToAdd={() => setAllowMapClickToAdd((prev) => !prev)}
        onTriggerBurst={handleTriggerBurst} 
        onOpenAddModal={handleOpenAddModal}
        onEditObject={handleEditObject}
      />
      <div className="map-pane">
        <TacticalMap 
          tracks={tracks} 
          ewNodes={ewNodes} 
          zones={zones}
          sensors={sensors}
          onMapClick={handleMapClick}
          onDeleteZone={handleDeleteZone}
          onDeleteSensor={handleDeleteSensor}
          onDeleteEW={handleDeleteEW}
          onEditObject={handleEditObject}
          onDragStart={handleDragStart}
          onCommitMoveEW={handleCommitMoveEW}
          onCommitMoveSensor={handleCommitMoveSensor}
          onCommitMoveZone={handleCommitMoveZone}
        />
      </div>

      {isModalOpen && (
        <TacticalObjectModal
          initialLat={selectedCoords.lat}
          initialLon={selectedCoords.lon}
          editingObject={editingObject}
          onClose={() => {
            setIsModalOpen(false);
            setEditingObject(null);
          }}
          onSuccess={() => {
            setIsModalOpen(false);
            setEditingObject(null);
          }}
        />
      )}
    </div>
  );
};

export default App;