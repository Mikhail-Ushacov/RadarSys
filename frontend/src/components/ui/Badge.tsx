import React from 'react';
import styles from './Badge.module.css';

type Tone = 'safe' | 'caution' | 'danger' | 'info' | 'neutral' | 'armed' | 'jamming';

export const Badge: React.FC<{ tone?: Tone; children: React.ReactNode; className?: string }> = ({
  tone = 'neutral',
  children,
  className = '',
}) => {
  const cls = tone === 'armed' ? 'caution' : tone;
  return <span className={`${styles.root} ${styles[cls]} t-mono${className ? ` ${className}` : ''}`}>{children}</span>;
};
