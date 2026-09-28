import React from 'react';
import styles from './Button.module.css';

type Variant = 'primary' | 'default' | 'danger' | 'ghost' | 'success';

interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  active?: boolean;
}

export const Button: React.FC<Props> = ({ variant = 'default', active = false, className = '', ...rest }) => {
  const cls = [styles.root, styles[variant], active ? styles.active : '', className]
    .filter(Boolean)
    .join(' ');
  return <button className={cls} {...rest} />;
};
