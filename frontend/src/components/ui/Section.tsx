import React from 'react';
import styles from './Section.module.css';

export const Section: React.FC<{ title?: string; action?: React.ReactNode; children: React.ReactNode }> = ({
  title,
  action,
  children,
}) => {
  return (
    <section className={styles.root}>
      {(title || action) && (
        <div className={styles.head}>
          {title && <h4 className={styles.title}>{title}</h4>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
};
