import React from 'react';
import styles from './Toggle.module.css';

export const Toggle: React.FC<{ on: boolean; onChange: () => void; label?: string }> = ({ on, onChange, label }) => {
  return (
    <button className={`${styles.root}${on ? ` ${styles.on}` : ''}`} onClick={onChange} aria-pressed={on}>
      {label && <span>{label}</span>}
      <span className={styles.pill}>
        <span className={styles.knob} />
      </span>
    </button>
  );
};
