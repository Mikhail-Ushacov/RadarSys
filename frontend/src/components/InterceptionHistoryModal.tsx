// // frontend/src/components/InterceptionHistoryModal.tsx
// import React, { useState, useEffect } from 'react';
// import { X, ShieldAlert, CheckCircle2, RotateCcw, Crosshair, MapPin, Clock } from 'lucide-react';
// import { DownedDroneDetailed } from '../types';

// interface Props {
//   onClose: () => void;
// }

// export const InterceptionHistoryModal: React.FC<Props> = ({ onClose }) => {
//   const [history, setHistory] = useState<DownedDroneDetailed[]>([]);
//   const [loading, setLoading] = useState(true);
//   const [searchTerm, setSearchTerm] = useState('');
//   const backendUrl = `http://${window.location.hostname}:8000`;

//   const fetchHistory = async () => {
//     try {
//       setLoading(true);
//       const res = await fetch(`${backendUrl}/api/v1/downed_drones`);
//       const data = await res.json();
//       setHistory(data || []);
//     } catch (err) {
//       console.error('Помилка завантаження журналу:', err);
//     } finally {
//       setLoading(false);
//     }
//   };

//   useEffect(() => {
//     fetchHistory();
//   }, []);

//   const handleClearHistory = async () => {
//     if (!window.confirm('Очистити всю історію перехоплень?')) return;
//     await fetch(`${backendUrl}/api/v1/downed_drones`, { method: 'DELETE' });
//     setHistory([]);
//   };

//   const filtered = history.filter((d) => 
//     d.drone_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
//     d.target_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
//     d.interceptor_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
//     d.crash_zone.toLowerCase().includes(searchTerm.toLowerCase())
//   );

//   return (
//     <div className="modal-overlay">
//       <div className="history-modal">
//         <div className="modal-header">
//           <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
//             <CheckCircle2 size={22} color="#10b981" />
//             <h3 style={{ fontSize: '1.1rem', margin: 0, letterSpacing: '0.05em' }}>
//               ЖУРНАЛ БОЙОВОЇ РОБОТИ ТА ЗБИТИХ ДРОНІВ (Всього: {history.length})
//             </h3>
//           </div>
//           <div style={{ display: 'flex', gap: '8px' }}>
//             <button onClick={fetchHistory} className="btn-secondary" title="Оновити">
//               <RotateCcw size={14} />
//             </button>
//             <button onClick={handleClearHistory} className="btn-popup-delete" title="Очистити історію">
//               Очистити
//             </button>
//             <button onClick={onClose} className="btn-close"><X size={20} /></button>
//           </div>
//         </div>

//         <div style={{ padding: '0.8rem 1.2rem', display: 'flex', gap: '10px' }}>
//           <input
//             type="text"
//             placeholder="Пошук за бортовим номером, об'єктом, РЕБ або сектором..."
//             value={searchTerm}
//             onChange={(e) => setSearchTerm(e.target.value)}
//             className="tactical-input"
//             style={{ flex: 1 }}
//           />
//         </div>

//         <div className="history-table-wrapper">
//           {loading ? (
//             <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>Завантаження даних...</div>
//           ) : filtered.length === 0 ? (
//             <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Збитих дронів не зафіксовано</div>
//           ) : (
//             <table className="tactical-table">
//               <thead>
//                 <tr>
//                   <th>Бортовий номер</th>
//                   <th>Час спавну</th>
//                   <th>Час збиття</th>
//                   <th>Точка появи (WGS-84)</th>
//                   <th>Ціль атаки ворога</th>
//                   <th>Комплекс РЕБ</th>
//                   <th>Точка падіння</th>
//                   <th>Зона падіння</th>
//                   <th>Статус</th>
//                 </tr>
//               </thead>
//               <tbody>
//                 {filtered.map((row) => (
//                   <tr key={row.id}>
//                     <td><strong style={{ color: '#f87171' }}>{row.drone_id}</strong></td>
//                     <td style={{ color: '#94a3b8' }}>{row.spawn_time}</td>
//                     <td style={{ color: '#38bdf8' }}>{row.downed_time}</td>
//                     <td style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{row.spawn_coords}</td>
//                     <td><b style={{ color: '#fbbf24' }}>{row.target_name}</b></td>
//                     <td><span style={{ color: '#a78bfa', fontWeight: 'bold' }}>{row.interceptor_name}</span></td>
//                     <td style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{row.crash_coords}</td>
//                     <td><span style={{ color: '#34d399' }}>{row.crash_zone}</span></td>
//                     <td>
//                       <span className="badge badge-safe">💥 {row.status}</span>
//                     </td>
//                   </tr>
//                 ))}
//               </tbody>
//             </table>
//           )}
//         </div>
//       </div>
//     </div>
//   );
// };