import React, { useState } from 'react';
import { Track, EWNode, TacticalSensor, TacticalZone, DownedDroneDetailed } from '../types';
import {
  Crosshair, Zap, Plus, Camera, Mic,
  Eye, Target, ShieldAlert, ShieldCheck, AlertTriangle, Edit3,
  Play, Square, RotateCcw, Grid, Compass,
  AlertOctagon, History, ArrowRight, PenTool, Sparkles, Database, Users
} from 'lucide-react';
import { EditableObject } from './TacticalObjectModal';
import { Button } from './ui/Button';
import { Badge } from './ui/Badge';
import { Section } from './ui/Section';
import { Toggle } from './ui/Toggle';
import styles from './TargetHUD.module.css';

interface Props {
  tracks: Track[];
  ewNodes: EWNode[];
  sensors: TacticalSensor[];
  zones: TacticalZone[];
  recentDowned: DownedDroneDetailed[];
  totalDownedCount: number;
  allowMapClickToAdd: boolean;
  isDrawingZone: boolean;
  simulationActive: boolean;
  autoTracking: boolean;
  emergencyOverride: boolean;
  threatInfo: string | null;
  onToggleMapClickToAdd: () => void;
  onStartDrawingZone: () => void;
  onGenerateFromH3: () => void;
  onToggleSimulation: () => void;
  onToggleAutoTracking: () => void;
  onResetSimulation: () => void;
  onResetGrid: () => void;
  onTriggerBurst: (nodeId: number) => void;
  onOpenAddModal: () => void;
  onEditObject: (obj: EditableObject) => void;
  onOpenHistoryPage: () => void;
  onSeedData?: () => void;
  onOptimizeEW?: () => Promise<void> | void;
}

export const TargetHUD: React.FC<Props> = ({
  tracks, ewNodes, sensors, zones, recentDowned, totalDownedCount,
  allowMapClickToAdd, isDrawingZone, simulationActive, autoTracking, emergencyOverride, threatInfo,
  onToggleMapClickToAdd, onStartDrawingZone, onGenerateFromH3, onToggleSimulation, onToggleAutoTracking,
  onResetSimulation, onResetGrid, onTriggerBurst, onOpenAddModal, onEditObject, onOpenHistoryPage, onSeedData,
  onOptimizeEW
}) => {
  const [seeding, setSeeding] = useState(false);

  const handleSeed = async () => {
    if (onSeedData) {
      onSeedData();
      return;
    }
    try {
      setSeeding(true);
      const res = await fetch(`http://${window.location.hostname}:8000/api/v1/seed`, { method: 'POST' });
      if (res.ok) {
        alert('Базу даних успішно наповнено новими тактичними сенсорами, камерами, РЕБ та зонами!');
      }
    } catch (e) {
      console.error('Помилка виконання seed:', e);
    } finally {
      setSeeding(false);
    }
  };

  const [isOptimizing, setIsOptimizing] = useState(false);

  const handleRunOptimization = async () => {
    if (!confirm('Перерахувати оптимальні позиції комплексів РЕБ за даними H3 та ОКІ?')) return;
    try {
      setIsOptimizing(true);
      if (onOptimizeEW) {
        await onOptimizeEW();
      } else {
        const res = await fetch(`http://${window.location.hostname}:8000/api/v1/ew/optimize?node_count=5&replace=true`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
          alert(`Успішно оптимізовано ${data.count} комплексів РЕБ!`);
        }
      }
    } catch (e) {
      console.error(e);
      alert('Помилка оптимізації РЕБ');
    } finally {
      setIsOptimizing(false);
    }
  };

  return (
    <div className={styles.root}>
      <div className={styles.head}>
        <h2 className={styles.brand}>
          <Crosshair size={20} color="var(--info)" /> SURGICAL C2 EW
        </h2>
        <div className={styles.headActions}>
          <Button variant="ghost" onClick={onOpenHistoryPage} title="Перейти до повного журналу збиттів">
            <History size={14} /> ЖУРНАЛ ({totalDownedCount})
          </Button>
          <Button variant="primary" onClick={onOpenAddModal} title="Додати новий об'єкт або зону вручну">
            <Plus size={15} /> ДОДАТИ
          </Button>
        </div>
      </div>
      <div className={styles.optBar}>
        <Button variant="default" onClick={handleRunOptimization} disabled={isOptimizing} title="Автоматичний розрахунок оптимальних рубежів РЕБ">
          <Compass size={12} /> {isOptimizing ? 'Розрахунок...' : 'Оптимізувати РЕБ'}
        </Button>
      </div>

      {threatInfo && (
        <div className={`${styles.alert}${emergencyOverride ? ` ${styles.alertCritical}` : ''}`}>
          <div className={styles.alertTitle}>
            <AlertOctagon size={16} /> ТАКТИЧНА ДІЯ:
          </div>
          <div className={styles.alertBody}>
            {threatInfo}
          </div>
        </div>
      )}

      <div className={styles.panel}>
        <div className={styles.panelRow}>
          <span className={styles.panelLabel}>РЕЖИМ СУПРОВОДУ:</span>
          <Button variant={autoTracking ? 'primary' : 'default'} onClick={onToggleAutoTracking}>
            <Compass size={11} /> {autoTracking ? 'LEAD-ANGLE ON' : 'MANUAL'}
          </Button>
        </div>

        <div className={styles.btnRow}>
          <Button
            variant={simulationActive ? 'danger' : 'success'}
            onClick={onToggleSimulation}
          >
            {simulationActive ? <><Square size={13} /> ПАУЗА</> : <><Play size={13} /> СТАРТ</>}
          </Button>
          <Button variant="default" onClick={onResetSimulation} title="Перезапустити випадкову появу дрона за містом">
            <RotateCcw size={14} />
          </Button>
          <Button variant="primary" onClick={handleSeed} disabled={seeding} title="Завантажити новий логічний Seed (камери, мікрофони, МВГ, РЕБ)">
            <Database size={14} />
          </Button>
          <Button variant="default" onClick={onResetGrid} title="Очистити всі зони, сенсори та вузли РЕБ">
            <Grid size={14} />
          </Button>
        </div>

        <div className={styles.zoneGrid}>
          <Button
            variant="default"
            onClick={onGenerateFromH3}
            title="Об'єднати H3 гексагони у суцільні райони безпеки"
          >
            <Sparkles size={12} /> Згенерувати з H3
          </Button>
          <Button
            variant="default"
            active={isDrawingZone}
            onClick={onStartDrawingZone}
            title="Малювати зону довільної форми кліками на карті"
          >
            <PenTool size={12} /> {isDrawingZone ? 'Малювання...' : 'Вільна форма'}
          </Button>
        </div>
      </div>

      <div className={styles.panel}>
        <Toggle
          on={allowMapClickToAdd}
          onChange={onToggleMapClickToAdd}
          label="Клік на карті (додати точку)"
        />
      </div>

      <div className={styles.scroll}>
        <Section title="Повітряна обстановка (БПЛА)" action={<span className="t-mono">{tracks.filter(t => t.status !== 'CRASHED').length}</span>}>
          {tracks.length === 0 ? (
            <div className={styles.empty}>
              Цілей у зоні виявлення немає.<br />
              Дрон летить за містом, очікується фіксація сенсорами або камерами...
            </div>
          ) : (
            tracks.map((t) => {
              const isInitial = t.detection_stage === 'INITIAL_CONTACT' || t.status === 'DETECTING';
              const tone = t.status === 'CRASHED' ? 'danger' :
                t.status === 'JAMMED' ? 'armed' :
                isInitial ? 'caution' :
                t.is_ci_critical ? 'jamming' :
                (t.is_safe_to_engage ? 'safe' : 'danger');
              return (
                <div
                  key={t.id}
                  className={styles.card}
                >
                  <div className={styles.cardHead}>
                    <span className={styles.cardTitle}>
                      {t.id}
                    </span>
                    <Badge tone={tone}>
                      {t.status === 'CRASHED' ? 'ЗБИТО' :
                        t.status === 'JAMMED' ? 'ПРИДУШЕНО' :
                        isInitial ? '1-Й КОНТАКТ' :
                        t.is_ci_critical ? 'CI CRITICAL THREAT' :
                        (t.is_safe_to_engage ? 'KILLBOX CLEAR' : 'NO-STRIKE ZONE')}
                    </Badge>
                  </div>

                  <div className={styles.cardBody}>
                    {isInitial ? (
                      <div>
                        <div className={styles.lead}>
                          <AlertTriangle size={13} /> Засічка: {t.last_sensor}
                        </div>
                        <div className={styles.note}>
                          Вектор швидкості, курс та ціль НЕВІДОМІ. Очікується 2-й контакт для визначення кінематики.
                        </div>
                      </div>
                    ) : (
                      <div>
                        <div className={`${styles.split} t-mono`}>
                          <span>Швидкість: <b>{t.speed !== null ? `${(t.speed * 3.6).toFixed(0)} км/год` : '?'}</b></span>
                          <span>Курс: <b>{t.heading !== null ? `${t.heading.toFixed(0)}°` : '?'}</b></span>
                        </div>
                        <div className="t-mono">Висота: <b>{t.alt.toFixed(0)} м</b> | Засічок: <b>{t.detection_count || 2}</b></div>

                        {t.kinematics_note && (
                          <div className={`${styles.note} t-mono`}>
                            {t.kinematics_note}
                          </div>
                        )}

                        {t.target_asset_name && (
                          <div className={styles.note}>
                            Ймовірна ціль: <b>{t.target_asset_name}</b>
                          </div>
                        )}

                        {t.nearest_ci && (
                          <div className={styles.note}>
                            До {t.nearest_ci}: <b className="t-mono">{t.ci_distance} м</b>
                          </div>
                        )}

                        {t.crash_safety !== null && t.crash_safety !== undefined && (
                          <div className={styles.note}>
                            Безпека падіння: <Badge tone={t.crash_safety >= 60 ? 'safe' : t.crash_safety >= 40 ? 'caution' : 'danger'}>{t.crash_safety.toFixed(1)}%</Badge>
                          </div>
                        )}

                        {t.detection_timeline && t.detection_timeline.length > 0 && (
                          <div className={styles.divider}>
                            <div className={styles.note}>ЛАНЦЮЖОК ВИЯВЛЕННЯ:</div>
                            {t.detection_timeline.map((line, idx) => (
                              <div key={idx} className={styles.note}>• {line}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </Section>

        <Section title="Останні збиті цілі" action={<span className="t-mono">Всього: {totalDownedCount}</span>}>
          {recentDowned.length === 0 ? (
            <p className={styles.note}>Журнал порожній (цілі ще не утилізовано)</p>
          ) : (
            <div className={styles.stack}>
              {recentDowned.map((d) => (
                <div key={d.id} className={styles.miniItem}>
                  <div className={styles.split}>
                    <strong className={styles.cardTitle}>{d.drone_id}</strong>
                    <span className={`${styles.note} t-mono`}>{d.downed_time.split(' ')[1] || d.downed_time}</span>
                  </div>
                  <div className={styles.note}>
                    Комплекс: <b>{d.interceptor_name}</b>
                  </div>
                  <div className={styles.note}>
                    Зона: {d.crash_zone}
                  </div>
                </div>
              ))}
            </div>
          )}

          <Button variant="ghost" onClick={onOpenHistoryPage} className={styles.fullWidth}>
            Повний журнал збиттів ({totalDownedCount}) <ArrowRight size={13} />
          </Button>
        </Section>

        <Section title={`Комплекси РЕБ (${ewNodes.length})`}>
          {ewNodes.map((n) => (
            <div key={n.id} className={`${styles.card}`}>
              <div className={styles.cardHead}>
                <span className={styles.cardTitle}>{n.name}</span>
                <div className={styles.row}>
                  <button onClick={() => onEditObject({ type: 'ew', data: n })} className={styles.iconBtn} title="Редагувати параметри РЕБ">
                    <Edit3 size={13} />
                  </button>
                  <Badge tone={n.is_transmitting ? 'jamming' : n.is_armed ? 'armed' : 'neutral'}>
                    {n.is_transmitting ? 'BURST ACTIVE' : n.is_armed ? 'TRACKING' : 'STANDBY'}
                  </Badge>
                </div>
              </div>
              <div className={`${styles.cardBody} t-mono`}>
                Кут: <b>{n.azimuth}°</b> | Промінь: <b>{n.beamwidth}°</b> | R: <b>{n.max_range}м</b>
              </div>
              <Button
                variant={n.is_transmitting ? 'danger' : 'primary'}
                onClick={() => onTriggerBurst(n.id)}
                disabled={n.is_transmitting}
                className={styles.fullWidth}
              >
                <Zap size={14} /> {n.is_transmitting ? 'АКТИВНЕ ПРИДУШЕННЯ...' : '20s ПРИМУСОВИЙ BURST'}
              </Button>
            </div>
          ))}
        </Section>

        <Section title={`Сенсори та об'єкти (${sensors.length})`}>
          {sensors.map((s) => (
            <div key={s.id} className={`${styles.card} ${styles.row}`}>
              {s.sensor_type === 'camera' && <Camera size={16} />}
              {s.sensor_type === 'acoustic' && <Mic size={16} />}
              {s.sensor_type === 'observation_post' && <Eye size={16} />}
              {s.sensor_type === 'target_asset' && <Target size={16} />}
              {s.sensor_type === 'witness_report' && <Users size={16} />}
              <div className={`${styles.cardBody} ${styles.grow}`}>
                <div className={styles.strong}>{s.name}</div>
                <div>R: <span className="t-mono">{s.detection_radius}м</span> {s.description ? `• ${s.description}` : ''}</div>
              </div>
              <button onClick={() => onEditObject({ type: 'sensor', data: s })} className={styles.iconBtn} title="Редагувати">
                <Edit3 size={13} />
              </button>
            </div>
          ))}
        </Section>

        <Section title={`Тактичні райони (${zones.length})`}>
          {zones.map((z) => (
            <div key={z.id} className={`${styles.card} ${styles.split}`}>
              <span className={`${styles.cardBody} ${styles.row}`}>
                {z.zone_type === 'safe' && <ShieldCheck size={14} />}
                {z.zone_type === 'caution' && <AlertTriangle size={14} />}
                {z.zone_type === 'danger' && <ShieldAlert size={14} />}
                {z.name}
              </span>
              <div className={styles.row}>
                <button onClick={() => onEditObject({ type: 'zone', data: z })} className={styles.iconBtn} title="Редагувати зону">
                  <Edit3 size={13} />
                </button>
                <Badge tone={z.zone_type === 'safe' ? 'safe' : z.zone_type === 'caution' ? 'caution' : 'danger'}>
                  {z.zone_type === 'safe' ? 'KILLBOX' : z.zone_type === 'caution' ? 'CAUTION' : 'NO-DROP'}
                </Badge>
              </div>
            </div>
          ))}
        </Section>

      </div>
    </div>
  );
};
