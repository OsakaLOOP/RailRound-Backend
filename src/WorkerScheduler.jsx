import React, { useState, useEffect } from 'react';
import { Play, Repeat, StopCircle, Save } from 'lucide-react';

const WorkerScheduler = () => {
    const [workers, setWorkers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editPeriods, setEditPeriods] = useState({});

    // --- Inline Styles ---
    const styles = {
        container: {
            padding: '24px',
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            boxSizing: 'border-box',
            backgroundColor: '#1e293b', // Match background color
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
        btnPrimary: {
            backgroundColor: '#3b82f6',
        },
        btnDanger: {
            backgroundColor: '#7f1d1d',
            border: '1px solid #b91c1c',
        },
        btnSuccess: {
            backgroundColor: '#22c55e',
        },
        btnDisabled: {
            backgroundColor: '#4b5563',
            color: '#9ca3af',
            cursor: 'not-allowed',
        },
        tableContainer: {
            flex: 1,
            overflow: 'auto',
            backgroundColor: '#1e293b',
            borderRadius: '8px',
            border: '1px solid #374151',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
        },
        table: {
            width: '100%',
            borderCollapse: 'collapse',
            textAlign: 'left',
        },
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
        tr: {
            transition: 'background-color 0.15s',
        },
        statusBadge: {
            display: 'inline-flex',
            alignItems: 'center',
            padding: '2px 10px',
            borderRadius: '9999px',
            fontSize: '0.75rem',
            fontWeight: '500',
        },
        statusRunning: { backgroundColor: '#dbeafe', color: '#1e40af' },
        statusDone: { backgroundColor: '#dcfce7', color: '#166534' },
        statusError: { backgroundColor: '#fee2e2', color: '#991b1b' },
        statusIdle: { backgroundColor: '#f3f4f6', color: '#1f2937' },

        progressBarBg: {
            width: '100%',
            backgroundColor: '#374151',
            borderRadius: '9999px',
            height: '10px',
            marginBottom: '4px',
            overflow: 'hidden',
        },
        progressBarFill: (percent) => ({
            height: '100%',
            backgroundColor: '#3b82f6',
            width: `${Math.min(Math.max(percent, 0), 100)}%`,
            transition: 'width 0.5s ease',
        }),
        progressStats: {
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: '0.75rem',
            color: '#9ca3af',
        },
        logPreview: {
            fontSize: '0.75rem',
            color: '#6b7280',
            marginTop: '4px',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            maxWidth: '200px',
        },
        inputPeriod: {
            backgroundColor: '#111827',
            border: '1px solid #4b5563',
            color: 'white',
            fontSize: '0.875rem',
            borderRadius: '4px',
            width: '80px',
            padding: '4px 8px',
            outline: 'none',
        },
        iconBtn: {
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: '#22c55e',
            padding: '4px',
            display: 'flex',
            alignItems: 'center',
        }
    };

    const fetchWorkers = async () => {
        try {
            if (window.pywebview && window.pywebview.api) {
                const data = await window.pywebview.api.get_workers_status();
                setWorkers(data || []);
            } else {
                // Mock data
                setWorkers([
                    {
                        id: "mock-1",
                        display_name: "Mock GeoJson",
                        type: "geojson",
                        status_code: 1,
                        status_text: "Running",
                        period: 3600,
                        progress: {
                            current: 50,
                            total: 100,
                            percent: 50,
                            eta_seconds: 10,
                            speed: 5
                        },
                        log_preview: "Processing..."
                    },
                    {
                        id: "mock-2",
                        display_name: "Mock Ekidata",
                        type: "ekidata",
                        status_code: 0,
                        status_text: "Idle",
                        period: 7200,
                        progress: {
                            current: 0,
                            total: 0,
                            percent: 0,
                            eta_seconds: 0,
                            speed: 0
                        },
                        log_preview: "Ready"
                    }
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

    const handleStartWorker = async (name) => {
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

    const savePeriod = async (name, id) => {
        const val = editPeriods[id];
        if (!val) return;

        if (window.pywebview && window.pywebview.api) {
            await window.pywebview.api.update_worker_period(name, val);
            setEditPeriods(prev => {
                const next = { ...prev };
                delete next[id];
                return next;
            });
            fetchWorkers();
        } else {
            console.log(`Simulating update period for ${name}: ${val}`);
        }
    };

    const getStatusStyle = (code) => {
        if (code === 1) return styles.statusRunning;
        if (code === 200) return styles.statusDone;
        if (code === 500) return styles.statusError;
        return styles.statusIdle;
    };

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

                             return (
                                <tr
                                    key={worker.id}
                                    style={styles.tr}
                                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#1f2937'}
                                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
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
                                        <div style={styles.logPreview} title={worker.log_preview}>
                                            {worker.log_preview}
                                        </div>
                                    </td>
                                    <td style={styles.td}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                            <input
                                                type="number"
                                                style={styles.inputPeriod}
                                                value={editPeriods[worker.id] !== undefined ? editPeriods[worker.id] : (worker.period || '')}
                                                onChange={(e) => handlePeriodChange(worker.id, e.target.value)}
                                            />
                                            {editPeriods[worker.id] !== undefined && (
                                                <button
                                                    onClick={() => savePeriod(worker.display_name, worker.id)}
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
                                            onClick={() => handleStartWorker(worker.display_name)}
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
        </div>
    );
};

export default WorkerScheduler;
