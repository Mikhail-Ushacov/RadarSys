// frontend/src/components/ui/ModeSwitcher.tsx
import React from 'react';
import { Radio, Cpu } from 'lucide-react';
import { DataSourceMode } from '../../types';
import s from './ModeSwitcher.module.css';

interface Props {
  mode: DataSourceMode;
  mapaFeedMode?: 'live' | 'replay';
  onChangeMode: (newMode: DataSourceMode) => void;
}

export const ModeSwitcher: React.FC<Props> = ({ mode, mapaFeedMode = 'live', onChangeMode }) => {
  const isMapa = mode === 'live_mapa';

  return (
    <div className={s.container}>
      <div className={s.labelRow}>
        <span>ДЖЕРЕЛО ПОВІТРЯНИХ ЦІЛЕЙ:</span>
        {isMapa && (
          <span className={s.badgeLive}>
            <span className={s.pulseDot} />
            {mapaFeedMode === 'live' ? 'MAPA.UA LIVE' : 'MAPA.UA (ОСТАННІЙ НАЛЬОТ)'}
          </span>
        )}
      </div>

      <div className={s.sliderTrack}>
        <button
          type="button"
          className={`${s.segment} ${!isMapa ? s.segmentActive : ''}`}
          onClick={() => onChangeMode('simulation')}
        >
          <Cpu size={13} />
          СИМУЛЯЦІЯ
        </button>

        <button
          type="button"
          className={`${s.segment} ${isMapa ? s.segmentActive : ''}`}
          onClick={() => onChangeMode('live_mapa')}
        >
          <Radio size={13} />
          MAPA.UA API
        </button>
      </div>

      <div className={s.metaInfo}>
        <span>
          {!isMapa ? 'Алгоритмічний спавн у секторі' : 'Радіолокаційні дані mapa.ua'}
        </span>
        <span className="t-mono">WGS84 ➔ ENU Flat-Earth</span>
      </div>
    </div>
  );
};