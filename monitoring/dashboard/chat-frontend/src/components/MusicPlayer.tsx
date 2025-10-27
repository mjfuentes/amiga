import React, { useEffect, useRef, useState } from 'react';
import './MusicPlayer.css';

export const MusicPlayer: React.FC = () => {
  const [isMuted, setIsMuted] = useState(() => {
    // Load mute preference from localStorage
    const saved = localStorage.getItem('musicPlayerMuted');
    return saved === 'true';
  });
  const audioContextRef = useRef<AudioContext | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const isPlayingRef = useRef(false);
  const nextNoteTimeRef = useRef(0);
  const schedulerIdRef = useRef<number | null>(null);

  // Tetris-like melody (A-Type theme inspired)
  // Notes in format: [frequency, duration]
  const melody: [number, number][] = [
    [659.25, 0.4], // E5
    [493.88, 0.2], // B4
    [523.25, 0.2], // C5
    [587.33, 0.4], // D5
    [523.25, 0.2], // C5
    [493.88, 0.2], // B4
    [440.00, 0.4], // A4
    [440.00, 0.2], // A4
    [523.25, 0.2], // C5
    [659.25, 0.4], // E5
    [587.33, 0.2], // D5
    [523.25, 0.2], // C5
    [493.88, 0.6], // B4
    [523.25, 0.2], // C5
    [587.33, 0.4], // D5
    [659.25, 0.4], // E5
    [523.25, 0.4], // C5
    [440.00, 0.4], // A4
    [440.00, 0.4], // A4
    [0, 0.4], // Rest
    [587.33, 0.6], // D5
    [698.46, 0.2], // F5
    [880.00, 0.4], // A5
    [783.99, 0.2], // G5
    [698.46, 0.2], // F5
    [659.25, 0.6], // E5
    [523.25, 0.2], // C5
    [659.25, 0.4], // E5
    [587.33, 0.2], // D5
    [523.25, 0.2], // C5
    [493.88, 0.4], // B4
    [493.88, 0.2], // B4
    [523.25, 0.2], // C5
    [587.33, 0.4], // D5
    [659.25, 0.4], // E5
    [523.25, 0.4], // C5
    [440.00, 0.4], // A4
    [440.00, 0.4], // A4
  ];

  const currentNoteRef = useRef(0);

  const createOscillator = (audioContext: AudioContext, frequency: number, startTime: number, duration: number, gainNode: GainNode) => {
    if (frequency === 0) return; // Rest

    const oscillator = audioContext.createOscillator();
    const noteGain = audioContext.createGain();

    // Square wave for 8-bit sound
    oscillator.type = 'square';
    oscillator.frequency.value = frequency;

    // ADSR envelope for more authentic chiptune sound
    const attackTime = 0.01;
    const decayTime = 0.05;
    const sustainLevel = 0.6;
    const releaseTime = 0.05;

    noteGain.gain.setValueAtTime(0, startTime);
    noteGain.gain.linearRampToValueAtTime(0.3, startTime + attackTime);
    noteGain.gain.linearRampToValueAtTime(sustainLevel * 0.3, startTime + attackTime + decayTime);
    noteGain.gain.setValueAtTime(sustainLevel * 0.3, startTime + duration - releaseTime);
    noteGain.gain.linearRampToValueAtTime(0, startTime + duration);

    oscillator.connect(noteGain);
    noteGain.connect(gainNode);

    oscillator.start(startTime);
    oscillator.stop(startTime + duration);
  };

  const scheduleNote = () => {
    if (!audioContextRef.current || !gainNodeRef.current || !isPlayingRef.current) return;

    const audioContext = audioContextRef.current;
    const gainNode = gainNodeRef.current;
    const scheduleAheadTime = 0.1; // Schedule notes 100ms ahead

    while (nextNoteTimeRef.current < audioContext.currentTime + scheduleAheadTime) {
      const [frequency, duration] = melody[currentNoteRef.current];
      createOscillator(audioContext, frequency, nextNoteTimeRef.current, duration, gainNode);

      nextNoteTimeRef.current += duration;
      currentNoteRef.current = (currentNoteRef.current + 1) % melody.length;
    }

    schedulerIdRef.current = window.setTimeout(scheduleNote, 25); // Check every 25ms
  };

  const startMusic = async () => {
    if (isPlayingRef.current) return;

    try {
      // Create AudioContext on user interaction (browser requirement)
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
        gainNodeRef.current = audioContextRef.current.createGain();
        gainNodeRef.current.connect(audioContextRef.current.destination);

        // Set initial volume (40% for background music)
        gainNodeRef.current.gain.value = isMuted ? 0 : 0.4;
      }

      // Resume context if suspended (browser autoplay policy)
      if (audioContextRef.current.state === 'suspended') {
        await audioContextRef.current.resume();
      }

      isPlayingRef.current = true;
      nextNoteTimeRef.current = audioContextRef.current.currentTime;
      currentNoteRef.current = 0;
      scheduleNote();
    } catch (error) {
      console.error('Failed to start music:', error);
    }
  };

  const stopMusic = () => {
    if (schedulerIdRef.current) {
      window.clearTimeout(schedulerIdRef.current);
      schedulerIdRef.current = null;
    }
    isPlayingRef.current = false;
  };

  const toggleMute = () => {
    const newMutedState = !isMuted;
    setIsMuted(newMutedState);
    localStorage.setItem('musicPlayerMuted', String(newMutedState));

    if (gainNodeRef.current) {
      gainNodeRef.current.gain.value = newMutedState ? 0 : 0.4;
    }
  };

  useEffect(() => {
    // Wait for user interaction to start music (browser autoplay policy)
    const handleUserInteraction = async () => {
      await startMusic();
      document.removeEventListener('click', handleUserInteraction);
      document.removeEventListener('keydown', handleUserInteraction);
    };

    document.addEventListener('click', handleUserInteraction);
    document.addEventListener('keydown', handleUserInteraction);

    // Cleanup
    return () => {
      stopMusic();
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
      document.removeEventListener('click', handleUserInteraction);
      document.removeEventListener('keydown', handleUserInteraction);
    };
  }, []);

  // Update volume when mute state changes
  useEffect(() => {
    if (gainNodeRef.current) {
      gainNodeRef.current.gain.value = isMuted ? 0 : 0.4;
    }
  }, [isMuted]);

  return (
    <div className="music-player">
      <button
        className={`music-toggle ${isMuted ? 'muted' : 'playing'}`}
        onClick={toggleMute}
        aria-label={isMuted ? 'Unmute background music' : 'Mute background music'}
        title={isMuted ? 'Unmute background music' : 'Mute background music'}
      >
        {isMuted ? (
          // Muted icon
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M11 5L6 9H2v6h4l5 4V5z" />
            <line x1="23" y1="9" x2="17" y2="15" />
            <line x1="17" y1="9" x2="23" y2="15" />
          </svg>
        ) : (
          // Playing icon
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M11 5L6 9H2v6h4l5 4V5z" />
            <path d="M15.54 8.46a5 5 0 010 7.07" />
            <path d="M19.07 4.93a10 10 0 010 14.14" />
          </svg>
        )}
      </button>
    </div>
  );
};
