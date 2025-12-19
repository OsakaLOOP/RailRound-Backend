import React from 'react';
import { Activity, Clock, AlertCircle, CheckCircle, Terminal } from 'lucide-react';

const DEFAULT_MOCK_DATA = {
  id: "GeojsonWorker",
  display_name: "GeojsonWorker",
  type: "geojson_process",
  status_code: 1, // 1: Running
  status_text: "Running",
  progress: {
    current: 357,
    total: 1200,
    percent: 29.7,
    eta_seconds: 45,
    speed: 12.5,
    error: null,
    is_active: true
  },
  last_update_ts: Date.now() / 1000,
  log_preview: "Processing line: Hakodate Line..."
};

const WorkerProgressPanel = ({ workerData = DEFAULT_MOCK_DATA }) => {
  const { display_name, status_code, status_text, progress, log_preview } = workerData;
  const { percent, current, total, speed, eta_seconds, error } = progress;

  // Status Colors
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
      backgroundColor: '#1e293b', // Slate 800
      color: '#f8fafc', // Slate 50
      borderRadius: '8px',
      padding: '16px',
      fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
      maxWidth: '400px',
      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
      border: '1px solid #334155'
    },
    header: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '12px'
    },
    title: {
      fontSize: '1.125rem',
      fontWeight: '600',
      display: 'flex',
      alignItems: 'center',
      gap: '8px'
    },
    badge: {
      backgroundColor: statusColor,
      color: 'white',
      padding: '2px 8px',
      borderRadius: '9999px',
      fontSize: '0.75rem',
      fontWeight: '500',
      textTransform: 'uppercase'
    },
    progressBarContainer: {
      height: '8px',
      backgroundColor: '#334155',
      borderRadius: '4px',
      overflow: 'hidden',
      marginBottom: '12px'
    },
    progressBarFill: {
      height: '100%',
      width: `${Math.min(Math.max(percent, 0), 100)}%`,
      backgroundColor: statusColor,
      transition: 'width 0.5s ease-in-out'
    },
    statsGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(2, 1fr)',
      gap: '8px',
      marginBottom: '12px',
      fontSize: '0.875rem',
      color: '#cbd5e1'
    },
    statItem: {
      display: 'flex',
      alignItems: 'center',
      gap: '6px'
    },
    logPanel: {
      backgroundColor: '#0f172a', // Slate 900
      padding: '8px',
      borderRadius: '4px',
      fontSize: '0.75rem',
      fontFamily: 'monospace',
      color: '#94a3b8',
      display: 'flex',
      alignItems: 'flex-start',
      gap: '6px',
      minHeight: '40px'
    }
  };

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.title}>
          <Activity size={18} />
          <span>{display_name}</span>
        </div>
        <span style={styles.badge}>{status_text}</span>
      </div>

      {/* Progress Bar */}
      <div style={styles.progressBarContainer}>
        <div style={styles.progressBarFill} />
      </div>

      {/* Stats */}
      <div style={styles.statsGrid}>
        <div style={styles.statItem}>
          <CheckCircle size={14} />
          <span>{current} / {total} ({percent}%)</span>
        </div>
        <div style={styles.statItem}>
          <Activity size={14} />
          <span>{speed} / sec</span>
        </div>
        <div style={styles.statItem}>
          <Clock size={14} />
          <span>ETA: {eta_seconds}s</span>
        </div>
      </div>

      {/* Error Message (if any) */}
      {error && (
        <div style={{ ...styles.logPanel, color: '#f87171', marginBottom: '8px', backgroundColor: '#450a0a' }}>
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
      )}

      {/* Log Preview */}
      <div style={styles.logPanel}>
        <Terminal size={14} style={{ marginTop: '2px', flexShrink: 0 }} />
        <span style={{ wordBreak: 'break-all' }}>
          {log_preview || "Ready to start..."}
        </span>
      </div>
    </div>
  );
};

export default WorkerProgressPanel;
