/* SpriteCanvas — renders a sprite definition with idle / power animation.
   Usage:
     <SpriteCanvas draw={fn} scale={6} mode="idle" size={48|64} />

   Render strategy: synchronously paints the first frame inside the effect
   so the canvas is never blank — even if requestAnimationFrame is paused
   (hidden tab, html-to-image capture, etc). RAF then takes over for the
   live animation when the tab is visible.
*/

const { useEffect, useRef, useState } = React;

const SPRITE_SIZE = 48;

function SpriteCanvas({ draw, scale = 6, mode = 'idle', powerTrigger = 0, onPowerEnd, bg, label, size = SPRITE_SIZE }) {
  const canvasRef = useRef(null);
  const frameRef = useRef(0);
  const lastTickRef = useRef(0);
  const powerStartRef = useRef(null);
  const [activeMode, setActiveMode] = useState(mode);

  // When powerTrigger increments, switch into power mode for ~1.1s.
  useEffect(() => {
    if (powerTrigger > 0) {
      powerStartRef.current = performance.now();
      setActiveMode('power');
    }
  }, [powerTrigger]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = false;

    const paint = (now) => {
      // tick every 220ms for idle, 80ms for power (snappier)
      const interval = activeMode === 'power' ? 80 : 220;
      if (now - lastTickRef.current >= interval) {
        frameRef.current = (frameRef.current + 1) % 60;
        lastTickRef.current = now;
      }

      let t = 0;
      if (activeMode === 'power' && powerStartRef.current != null) {
        t = Math.min(1, (now - powerStartRef.current) / 1100);
        if (t >= 1) {
          setActiveMode('idle');
          powerStartRef.current = null;
          if (onPowerEnd) onPowerEnd();
        }
      }

      ctx.clearRect(0, 0, size, size);
      if (bg) {
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, size, size);
      }
      try {
        draw(ctx, frameRef.current, activeMode, t);
      } catch (e) {
        console.error('[SpriteCanvas] draw threw:', e);
      }
    };

    // Paint synchronously so the canvas is never blank.
    paint(performance.now());

    // Then animate via RAF (paused automatically when tab is hidden).
    let raf;
    const loop = (now) => {
      paint(now);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    // Fallback timer for hidden-tab scenarios (html-to-image captures, etc).
    // setInterval still fires when the tab is backgrounded (throttled).
    const fallback = setInterval(() => paint(performance.now()), 250);

    return () => {
      cancelAnimationFrame(raf);
      clearInterval(fallback);
    };
  }, [draw, activeMode, bg, onPowerEnd, size]);

  const displaySize = size * scale;
  return (
    <div style={{ position: 'relative', width: displaySize, height: displaySize }}>
      <canvas
        ref={canvasRef}
        width={size}
        height={size}
        style={{
          width: displaySize,
          height: displaySize,
          imageRendering: 'pixelated',
          display: 'block',
        }}
      />
      {label && (
        <div style={{
          position: 'absolute', top: 6, left: 6,
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 9, padding: '2px 5px',
          background: 'rgba(0,0,0,0.6)', color: '#9fd5ff',
          letterSpacing: 0.5, textTransform: 'uppercase',
          borderRadius: 2,
        }}>{label}</div>
      )}
    </div>
  );
}

window.SpriteCanvas = SpriteCanvas;
