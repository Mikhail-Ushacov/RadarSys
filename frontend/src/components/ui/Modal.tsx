import React from 'react';
import { X } from 'lucide-react';
import styles from './Modal.module.css';

export const Modal: React.FC<{ title: string; onClose: () => void; children: React.ReactNode; footer?: React.ReactNode }> = ({
  title,
  onClose,
  children,
  footer,
}) => {
  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.root} onClick={(e) => e.stopPropagation()}>
        <div className={styles.head}>
          <h3>{title}</h3>
          <button className={styles.close} onClick={onClose} aria-label="close">
            <X size={16} />
          </button>
        </div>
        <div>{children}</div>
        {footer && <div className={styles.foot}>{footer}</div>}
      </div>
    </div>
  );
};
