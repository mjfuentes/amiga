import React, { useState, useEffect, useRef, useCallback } from 'react';
import './ProjectSwitcher.css';

interface Project {
  name: string;
  path: string;
  primary_language: string;
  frameworks: string[];
}

export function ProjectSwitcher() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch('/api/projects');
      if (!res.ok) return;
      const data = await res.json();
      setProjects(data.projects || []);
      setActive(data.active || null);
    } catch {
      // Silently fail - projects feature may not be configured
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const switchProject = async (path: string) => {
    try {
      const res = await fetch('/api/projects/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      if (res.ok) {
        setActive(path);
        setIsOpen(false);
      }
    } catch {
      // Silently fail
    }
  };

  if (projects.length === 0) return null;

  const activeProject = projects.find((p) => p.path === active);

  return (
    <div className="project-switcher" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="project-switcher-btn"
        title={activeProject ? activeProject.path : 'Select project'}
      >
        <span className="project-switcher-icon">&#9671;</span>
        <span className="project-switcher-label">
          {activeProject ? activeProject.name : 'No project'}
        </span>
        <span className={`project-switcher-arrow ${isOpen ? 'open' : ''}`}>
          &#9662;
        </span>
      </button>
      {isOpen && (
        <div className="project-switcher-dropdown">
          {projects.map((p) => (
            <button
              key={p.path}
              className={`project-switcher-item ${p.path === active ? 'active' : ''}`}
              onClick={() => switchProject(p.path)}
              title={p.path}
            >
              <span className="project-item-name">{p.name}</span>
              <span className="project-item-lang">{p.primary_language}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
