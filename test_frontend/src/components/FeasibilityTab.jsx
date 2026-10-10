import React from 'react';
import { Cpu, HardDrive, Server, Zap, AlertTriangle, CheckCircle2, XCircle, Clock } from 'lucide-react';

export default function FeasibilityTab({ feasibility }) {
  if (!feasibility) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        No feasibility assessment data available.
      </div>
    );
  }

  const hw = feasibility.resource_assessment || {};
  const verdict = feasibility.verdict || 'feasible';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Verdict Banner */}
      <div style={{
        background: verdict === 'feasible' 
          ? 'rgba(16, 185, 129, 0.1)' 
          : verdict === 'feasible_with_limitations'
          ? 'rgba(245, 158, 11, 0.1)'
          : 'rgba(239, 68, 68, 0.1)',
        border: `1px solid ${
          verdict === 'feasible' 
            ? 'rgba(16, 185, 129, 0.3)' 
            : verdict === 'feasible_with_limitations'
            ? 'rgba(245, 158, 11, 0.3)'
            : 'rgba(239, 68, 68, 0.3)'
        }`,
        borderRadius: '0.75rem',
        padding: '1.25rem',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '1rem',
      }}>
        {verdict === 'feasible' ? (
          <CheckCircle2 size={24} color="#34d399" style={{ marginTop: '0.1rem' }} />
        ) : verdict === 'feasible_with_limitations' ? (
          <AlertTriangle size={24} color="#fbbf24" style={{ marginTop: '0.1rem' }} />
        ) : (
          <XCircle size={24} color="#f87171" style={{ marginTop: '0.1rem' }} />
        )}

        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.35rem' }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, textTransform: 'capitalize' }}>
              Execution Feasibility: {verdict.replace(/_/g, ' ')}
            </h3>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
              Assessed at {feasibility.checked_at ? new Date(feasibility.checked_at).toLocaleTimeString() : 'now'}
            </span>
          </div>

          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
            {verdict === 'feasible' && 'Host resources and container dependencies are fully sufficient to reproduce this experiment.'}
            {verdict === 'feasible_with_limitations' && 'Experiment can execute, but limitations exist (e.g. CPU-only execution or RAM bounds). Scientific parameters are preserved exactly and not altered.'}
            {verdict === 'blocked' && 'Execution cannot proceed in isolated containers under current host conditions.'}
          </p>

          {feasibility.reasons && feasibility.reasons.length > 0 && (
            <div style={{ marginTop: '0.75rem' }}>
              <strong style={{ fontSize: '0.8rem', color: '#f87171' }}>Blocking Reasons:</strong>
              <ul style={{ listStyleType: 'disc', paddingLeft: '1.5rem', fontSize: '0.8rem', color: '#fca5a5', marginTop: '0.25rem' }}>
                {feasibility.reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}

          {feasibility.warnings && feasibility.warnings.length > 0 && (
            <div style={{ marginTop: '0.75rem' }}>
              <strong style={{ fontSize: '0.8rem', color: '#fbbf24' }}>System Warnings:</strong>
              <ul style={{ listStyleType: 'disc', paddingLeft: '1.5rem', fontSize: '0.8rem', color: '#fde68a', marginTop: '0.25rem' }}>
                {feasibility.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Host Specifications Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            <Cpu size={18} color="var(--accent-blue)" />
            <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>Host CPU</span>
          </div>
          <div style={{ fontSize: '1.35rem', fontWeight: 700 }}>
            {hw.cpu_cores || 1} <span style={{ fontSize: '0.85rem', fontWeight: 400, color: 'var(--text-muted)' }}>Cores</span>
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            <Server size={18} color="var(--accent-indigo)" />
            <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>Available RAM</span>
          </div>
          <div style={{ fontSize: '1.35rem', fontWeight: 700 }}>
            {hw.ram_mb ? `${(hw.ram_mb / 1024).toFixed(1)} GB` : 'Unknown'}
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            <HardDrive size={18} color="var(--accent-cyan)" />
            <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>Free Disk Space</span>
          </div>
          <div style={{ fontSize: '1.35rem', fontWeight: 700 }}>
            {hw.disk_mb ? `${(hw.disk_mb / 1024).toFixed(1)} GB` : 'Unknown'}
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            <Zap size={18} color="var(--accent-green)" />
            <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>GPU Acceleration</span>
          </div>
          <div style={{ fontSize: '1.05rem', fontWeight: 700, color: hw.gpu_available ? '#34d399' : 'var(--text-dim)' }}>
            {hw.gpu_available ? hw.gpu_name || 'NVIDIA GPU' : 'None (CPU Execution)'}
          </div>
          {hw.gpu_memory_mb && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{hw.gpu_memory_mb} MB VRAM</span>
          )}
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            <Server size={18} color="var(--accent-purple)" />
            <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>Docker Daemon</span>
          </div>
          <div style={{ fontSize: '1.05rem', fontWeight: 700, color: hw.docker_available ? '#34d399' : '#f87171' }}>
            {hw.docker_available ? 'Available' : 'Unavailable'}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {hw.docker_version || 'Docker engine'}
          </span>
        </div>
      </div>

      {/* Node Requirements Table */}
      {feasibility.resource_requirements && feasibility.resource_requirements.length > 0 && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Per-Node Resource Estimates</h4>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              <Clock size={14} />
              <span>Est. Runtime: ~{feasibility.estimated_total_runtime_seconds || 0}s</span>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: '0.8rem', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
                  <th style={{ padding: '0.5rem' }}>Node ID</th>
                  <th style={{ padding: '0.5rem' }}>Estimated RAM</th>
                  <th style={{ padding: '0.5rem' }}>Estimated Disk</th>
                  <th style={{ padding: '0.5rem' }}>GPU Required</th>
                  <th style={{ padding: '0.5rem' }}>Est. Runtime</th>
                </tr>
              </thead>
              <tbody>
                {feasibility.resource_requirements.map((req) => (
                  <tr key={req.node_id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                    <td style={{ padding: '0.5rem', fontWeight: 600 }}>{req.node_id}</td>
                    <td style={{ padding: '0.5rem' }}>{req.estimated_ram_mb} MB</td>
                    <td style={{ padding: '0.5rem' }}>{req.estimated_disk_mb} MB</td>
                    <td style={{ padding: '0.5rem' }}>
                      <span className={`badge ${req.requires_gpu ? 'badge-amber' : 'badge-gray'}`}>
                        {req.requires_gpu ? 'GPU Required' : 'CPU Only'}
                      </span>
                    </td>
                    <td style={{ padding: '0.5rem' }}>{req.estimated_runtime_seconds}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
