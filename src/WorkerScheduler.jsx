import React, { useState, useEffect } from 'react';
import { Play, Repeat, StopCircle, Save, Activity, Clock, CheckCircle, AlertCircle } from 'lucide-react';

// Reusing style logic from previous WorkerProgressPanel but adapting for inline
const DetailProgressPanel = ({ workerData }) => {
  if (!workerData) return <div style={{padding: '20px', color: '#6b7280', textAlign: 'center'}}>Select a worker to view details</div>;

  const { display_name, status_code, status_text, progress, log_preview } = workerData;
  const { percent = 0, current = 0, total = 0, speed = 0, eta_seconds = 0, error } = progress || {};

  const getStatusColor = (code) => {
    switch (code) {
      case 1: return '#3b82f6'; // Blue (Running)
      case 200: return '#22c55e'; // Green (Done)
      case 500: return '#ef4444'; // Red (Error)
      default: return '#9ca3af'; // Gray (Idle/Unknown)
    }
  };

  const statusColor = getStatusColor(status_code);

  const styles = {
    container: {
      backgroundColor: '#0f172a',
      borderRadius: '8px',
      padding: '20px',
      border: '1px solid #334155',
      marginTop: '20px',
      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
    },
    header: {
      display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px'
    },
    title: { fontSize: '1.1rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px', color: 'white' },
    badge: { backgroundColor: statusColor, color: 'white', padding: '4px 12px', borderRadius: '9999px', fontSize: '0.75rem', fontWeight: 'bold', textTransform: 'uppercase' },
    progressBarContainer: { height: '12px', backgroundColor: '#334155', borderRadius: '6px', overflow: 'hidden', marginBottom: '16px' },
    progressBarFill: { height: '100%', width: `${Math.min(Math.max(percent, 0), 100)}%`, backgroundColor: statusColor, transition: 'width 0.5s ease' },
    statsGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '16px', color: '#cbd5e1' },
    statItem: { display: 'flex', flexDirection: 'column', gap: '4px', backgroundColor: '#1e293b', padding: '12px', borderRadius: '6px' },
    statLabel: { fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '6px' },
    statValue: { fontSize: '1.2rem', fontWeight: 'bold', color: 'white' },
    logPanel: { backgroundColor: '#1e293b', padding: '12px', borderRadius: '6px', fontFamily: 'monospace', fontSize: '0.8rem', color: '#94a3b8', border: '1px solid #334155', maxHeight: '100px', overflowY: 'auto' }
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div style={styles.title}><Activity size={20} /> {display_name} Details</div>
        <span style={styles.badge}>{status_text}</span>
      </div>

      <div style={styles.progressBarContainer}>
        <div style={styles.progressBarFill}></div>
      </div>

      <div style={styles.statsGrid}>
        <div style={styles.statItem}>
          <span style={styles.statLabel}><CheckCircle size={12} /> Progress</span>
          <span style={styles.statValue}>{current} / {total} ({percent}%)</span>
        </div>
        <div style={styles.statItem}>
          <span style={styles.statLabel}><Activity size={12} /> Speed</span>
          <span style={styles.statValue}>{speed}/s</span>
        </div>
        <div style={styles.statItem}>
          <span style={styles.statLabel}><Clock size={12} /> ETA</span>
          <span style={styles.statValue}>{eta_seconds}s</span>
        </div>
      </div>

      {error && (
        <div style={{ ...styles.logPanel, color: '#f87171', marginBottom: '12px', backgroundColor: '#450a0a', borderColor: '#7f1d1d' }}>
          <div style={{display:'flex', gap:'8px', alignItems:'center', marginBottom:'4px', fontWeight:'bold'}}><AlertCircle size={14}/> Error Occurred</div>
          {error}
        </div>
      )}

      <div style={styles.logPanel}>
        <div style={{marginBottom:'4px', fontSize:'0.7rem', textTransform:'uppercase', color:'#64748b'}}>Latest Log</div>
        {log_preview || "Ready..."}
      </div>
    </div>
  );
};


const WorkerScheduler = () => {
    const [workers, setWorkers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editPeriods, setEditPeriods] = useState({});
    const [selectedWorkerId, setSelectedWorkerId] = useState(null);

    // --- Inline Styles ---
    const styles = {
        container: {
            padding: '24px',
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            boxSizing: 'border-box',
            backgroundColor: '#1e293b',
            color: 'white',
        },
        header: {
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '24px',
        },
        title: {
            fontSize: '1.5rem',
            fontWeight: 'bold',
            margin: 0,
            color: 'white',
        },
        buttonGroup: {
            display: 'flex',
            gap: '12px',
        },
        btn: {
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            borderRadius: '4px',
            border: 'none',
            cursor: 'pointer',
            color: 'white',
            fontWeight: '500',
            transition: 'background-color 0.2s',
            fontSize: '14px',
        },
        btnPrimary: { backgroundColor: '#3b82f6' },
        btnDanger: { backgroundColor: '#7f1d1d', border: '1px solid #b91c1c' },
        btnSuccess: { backgroundColor: '#22c55e' },
        btnDisabled: { backgroundColor: '#4b5563', color: '#9ca3af', cursor: 'not-allowed' },

        tableContainer: {
            flex: 1,
            overflow: 'auto',
            backgroundColor: '#1e293b',
            borderRadius: '8px',
            border: '1px solid #374151',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
            minHeight: '200px' // Ensure visible even if empty
        },
        table: { width: '100%', borderCollapse: 'collapse', textAlign: 'left' },
        th: {
            backgroundColor: '#111827',
            color: '#9ca3af',
            textTransform: 'uppercase',
            fontSize: '0.75rem',
            padding: '16px',
            position: 'sticky',
            top: 0,
            zIndex: 10,
            borderBottom: '1px solid #374151',
            fontWeight: '600',
        },
        td: {
            padding: '16px',
            borderBottom: '1px solid #374151',
            color: '#e5e7eb',
            verticalAlign: 'middle',
        },
        tr: (isSelected) => ({
            transition: 'background-color 0.15s',
            cursor: 'pointer',
            backgroundColor: isSelected ? '#1e3a8a' : 'transparent', // Highlight selected
        }),
        statusBadge: {
            display: 'inline-flex', alignItems: 'center', padding: '2px 10px', borderRadius: '9999px', fontSize: '0.75rem', fontWeight: '500',
        },
        statusRunning: { backgroundColor: '#dbeafe', color: '#1e40af' },
        statusDone: { backgroundColor: '#dcfce7', color: '#166534' },
        statusError: { backgroundColor: '#fee2e2', color: '#991b1b' },
        statusIdle: { backgroundColor: '#f3f4f6', color: '#1f2937' },

        progressBarBg: { width: '100%', backgroundColor: '#374151', borderRadius: '9999px', height: '10px', marginBottom: '4px', overflow: 'hidden' },
        progressBarFill: (percent) => ({ height: '100%', backgroundColor: '#3b82f6', width: `${Math.min(Math.max(percent, 0), 100)}%`, transition: 'width 0.5s ease' }),
        progressStats: { display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#9ca3af' },
        inputPeriod: { backgroundColor: '#111827', border: '1px solid #4b5563', color: 'white', fontSize: '0.875rem', borderRadius: '4px', width: '80px', padding: '4px 8px', outline: 'none' },
        iconBtn: { background: 'none', border: 'none', cursor: 'pointer', color: '#22c55e', padding: '4px', display: 'flex', alignItems: 'center' }
    };

    const fetchWorkers = async () => {
        try {
            if (window.pywebview && window.pywebview.api) {
                const data = await window.pywebview.api.get_workers_status();
                setWorkers(data || []);
            } else {
                // Mock data
                setWorkers([
                    { id: "mock-1", display_name: "Mock GeoJson", type: "geojson", status_code: 1, status_text: "Running", period: 3600, progress: { current: 50, total: 100, percent: 50, eta_seconds: 10, speed: 5 }, log_preview: "Processing..." },
                    { id: "mock-2", display_name: "Mock Ekidata", type: "ekidata", status_code: 0, status_text: "Idle", period: 7200, progress: { current: 0, total: 0, percent: 0, eta_seconds: 0, speed: 0 }, log_preview: "Ready" }
                ]);
            }
        } catch (error) {
            console.error("Failed to fetch workers:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchWorkers();
        const interval = setInterval(fetchWorkers, 1000);
        return () => clearInterval(interval);
    }, []);

    const handleStartWorker = async (name, e) => {
        e.stopPropagation(); // Prevent row selection
        if (window.pywebview && window.pywebview.api) {
            await window.pywebview.api.start_worker(name);
            fetchWorkers();
        } else {
            console.log(`Simulating start worker: ${name}`);
        }
    };

    const handleStartFullCycle = async () => {
         if (window.pywebview && window.pywebview.api) {
            await window.pywebview.api.start_full_cycle();
            fetchWorkers();
        } else {
            console.log("Simulating start full cycle");
        }
    };

    const handleStopFullCycle = async () => {
        if (window.pywebview && window.pywebview.api) {
           await window.pywebview.api.stop_full_cycle();
           fetchWorkers();
       } else {
           console.log("Simulating stop full cycle");
       }
   };

    const handlePeriodChange = (id, value) => {
        setEditPeriods(prev => ({ ...prev, [id]: value }));
    };

    const savePeriod = async (name, id, e) => {
        e.stopPropagation(); // Prevent row select
        const val = editPeriods[id];
        if (!val) return;

        if (window.pywebview && window.pywebview.api) {
            await window.pywebview.api.update_worker_period(name, val);
            // Clear the edit state for this ID so the UI reverts to showing the worker.period (which should now be updated)
            setEditPeriods(prev => {
                const next = { ...prev };
                delete next[id];
                return next;
            });
            // Force fetch immediately to get updated data from backend
            await fetchWorkers();
        } else {
            console.log(`Simulating update period for ${name}: ${val}`);
            // Mock update
            setWorkers(prev => prev.map(w => w.id === id ? {...w, period: val} : w));
             setEditPeriods(prev => {
                const next = { ...prev };
                delete next[id];
                return next;
            });
        }
    };

    const getStatusStyle = (code) => {
        if (code === 1) return styles.statusRunning;
        if (code === 200) return styles.statusDone;
        if (code === 500) return styles.statusError;
        return styles.statusIdle;
    };

    const selectedWorker = workers.find(w => w.id === selectedWorkerId);

    return (
        <div style={styles.container}>
            <div style={styles.header}>
                <h2 style={styles.title}>Worker Scheduling</h2>
                <div style={styles.buttonGroup}>
                    <button
                        onClick={handleStopFullCycle}
                        style={{...styles.btn, ...styles.btnDanger}}
                        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#991b1b'}
                        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#7f1d1d'}
                    >
                        <StopCircle size={18} />
                        Stop Cycle
                    </button>
                    <button
                        onClick={handleStartFullCycle}
                        style={{...styles.btn, ...styles.btnPrimary}}
                        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#2563eb'}
                        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#3b82f6'}
                    >
                        <Repeat size={18} />
                        Run Full Cycle
                    </button>
                </div>
            </div>

            <div style={styles.tableContainer}>
                <table style={styles.table}>
                    <thead>
                        <tr>
                            <th style={styles.th}>Worker Name</th>
                            <th style={styles.th}>Type</th>
                            <th style={styles.th}>Status</th>
                            <th style={{...styles.th, width: '30%'}}>Progress</th>
                            <th style={styles.th}>Period (s)</th>
                            <th style={{...styles.th, textAlign: 'right'}}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {workers.length === 0 && !loading && (
                            <tr>
                                <td colSpan="6" style={{...styles.td, textAlign: 'center', color: '#6b7280'}}>
                                    No workers registered.
                                </td>
                            </tr>
                        )}

                        {workers.map((worker) => {
                             const progress = worker.progress || {};
                             const percent = progress.percent || 0;
                             const isRunning = worker.status_code === 1;
                             const isSelected = worker.id === selectedWorkerId;

                             return (
                                <tr
                                    key={worker.id}
                                    style={styles.tr(isSelected)}
                                    onClick={() => setSelectedWorkerId(worker.id)}
                                    onMouseEnter={(e) => {
                                        if(!isSelected) e.currentTarget.style.backgroundColor = '#1f2937';
                                    }}
                                    onMouseLeave={(e) => {
                                        if(!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
                                    }}
                                >
                                    <td style={{...styles.td, fontWeight: 500, color: 'white'}}>{worker.display_name}</td>
                                    <td style={{...styles.td, color: '#9ca3af', fontSize: '0.875rem'}}>{worker.type}</td>
                                    <td style={styles.td}>
                                        <span style={{...styles.statusBadge, ...getStatusStyle(worker.status_code)}}>
                                            {worker.status_text}
                                        </span>
                                    </td>
                                    <td style={styles.td}>
                                        <div style={styles.progressBarBg}>
                                            <div style={styles.progressBarFill(percent)}></div>
                                        </div>
                                        <div style={styles.progressStats}>
                                            <span>{progress.current || 0} / {progress.total || '?'}</span>
                                            <span>{progress.eta_seconds ? `ETA: ${progress.eta_seconds}s` : ''}</span>
                                        </div>
                                    </td>
                                    <td style={styles.td}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }} onClick={e => e.stopPropagation()}>
                                            <input
                                                type="number"
                                                style={styles.inputPeriod}
                                                value={editPeriods[worker.id] !== undefined ? editPeriods[worker.id] : (worker.period || '')}
                                                onChange={(e) => handlePeriodChange(worker.id, e.target.value)}
                                            />
                                            {editPeriods[worker.id] !== undefined && (
                                                <button
                                                    onClick={(e) => savePeriod(worker.display_name, worker.id, e)}
                                                    style={styles.iconBtn}
                                                    title="Save Period"
                                                >
                                                    <Save size={16} />
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                    <td style={{...styles.td, textAlign: 'right'}}>
                                        <button
                                            onClick={(e) => handleStartWorker(worker.display_name, e)}
                                            disabled={isRunning}
                                            style={{
                                                ...styles.btn,
                                                ...(isRunning ? styles.btnDisabled : styles.btnSuccess),
                                                display: 'inline-flex',
                                                padding: '6px 12px',
                                                fontSize: '0.875rem'
                                            }}
                                            onMouseEnter={(e) => {
                                                if(!isRunning) e.currentTarget.style.backgroundColor = '#16a34a';
                                            }}
                                            onMouseLeave={(e) => {
                                                if(!isRunning) e.currentTarget.style.backgroundColor = '#22c55e';
                                            }}
                                        >
                                            <Play size={14} />
                                            Run
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* Detail View */}
            <DetailProgressPanel workerData={selectedWorker} />
        </div>
    );
};

export default WorkerScheduler;
