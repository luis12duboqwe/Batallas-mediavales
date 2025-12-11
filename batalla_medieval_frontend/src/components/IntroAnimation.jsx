import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import castleSilhouette from '../assets/intro/castle-silhouette.svg';

const DURATION = 2500;

const IntroAnimation = ({ onComplete }) => {
  const canvasRef = useRef(null);
  const frameRef = useRef(null);
  const finishedRef = useRef(false);
  const navigate = useNavigate();
  const [showTitle, setShowTitle] = useState(false);
  const [fadeOut, setFadeOut] = useState(false);

  const finishSequence = useCallback(() => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    cancelAnimationFrame(frameRef.current);
    setShowTitle(true);
    setFadeOut(true);
    setTimeout(() => {
      onComplete?.();
      navigate('/login', { replace: true });
    }, 450);
  }, [navigate, onComplete]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');

    if (!canvas || !ctx) return undefined;

    finishedRef.current = false;
    const dpr = window.devicePixelRatio || 1;
    const fogLayers = [
      { x: -300, y: 80, speed: 0.05, opacity: 0.08, scale: 1.1 },
      { x: -150, y: 140, speed: 0.08, opacity: 0.12, scale: 1.3 },
      { x: -400, y: 200, speed: 0.04, opacity: 0.07, scale: 1.5 },
    ];
    const castleImage = new Image();
    castleImage.src = castleSilhouette;

    const resize = () => {
      const { clientWidth, clientHeight } = canvas;
      canvas.width = clientWidth * dpr;
      canvas.height = clientHeight * dpr;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(dpr, dpr);
    };

    resize();
    window.addEventListener('resize', resize);

    let start;

    const drawTorch = (x, y, intensity) => {
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, 90);
      gradient.addColorStop(0, `rgba(255, 193, 94, ${0.65 * intensity})`);
      gradient.addColorStop(0.4, `rgba(255, 160, 82, ${0.28 * intensity})`);
      gradient.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(x, y, 120, 0, Math.PI * 2);
      ctx.fill();
    };

    const drawFog = (layer) => {
      ctx.save();
      ctx.globalAlpha = layer.opacity;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      const fogGradient = ctx.createLinearGradient(0, 0, width, 0);
      fogGradient.addColorStop(0, 'rgba(255,255,255,0)');
      fogGradient.addColorStop(0.5, 'rgba(255,255,255,0.7)');
      fogGradient.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = fogGradient;
      ctx.filter = 'blur(18px)';
      ctx.fillRect(layer.x, layer.y, width * layer.scale, 140 * layer.scale);
      ctx.restore();
    };

    const drawCastle = (progress) => {
      if (!castleImage.complete) return;
      const width = canvas.clientWidth * 0.75;
      const height = width * (280 / 600);
      const x = (canvas.clientWidth - width) / 2;
      const y = canvas.clientHeight * 0.34;
      ctx.save();
      ctx.globalAlpha = Math.min(1, (progress - 0.35) / 0.35);
      ctx.drawImage(castleImage, x, y, width, height);
      ctx.restore();
    };

    const render = (timestamp) => {
      if (!start) start = timestamp;
      const elapsed = timestamp - start;
      const progress = Math.min(elapsed / DURATION, 1);

      const { clientWidth, clientHeight } = canvas;
      ctx.clearRect(0, 0, clientWidth, clientHeight);

      const bgGradient = ctx.createLinearGradient(0, 0, 0, clientHeight);
      bgGradient.addColorStop(0, '#04070d');
      bgGradient.addColorStop(1, '#0a0f1c');
      ctx.fillStyle = bgGradient;
      ctx.fillRect(0, 0, clientWidth, clientHeight);

      const torchIntensity = 0.8 + Math.sin(timestamp * 0.02) * 0.1 + Math.random() * 0.08;
      drawTorch(clientWidth * 0.25, clientHeight * 0.78, torchIntensity);
      drawTorch(clientWidth * 0.75, clientHeight * 0.78, torchIntensity * 0.92);

      fogLayers.forEach((layer) => {
        layer.x += layer.speed * 12;
        if (layer.x > clientWidth) layer.x = -clientWidth * 0.6;
        drawFog(layer);
      });

      if (progress > 0.35) {
        drawCastle(progress);
      }

      if (!showTitle && progress > 0.65) {
        setShowTitle(true);
      }

      const vignette = ctx.createRadialGradient(
        clientWidth / 2,
        clientHeight / 2,
        Math.max(clientWidth, clientHeight) * 0.1,
        clientWidth / 2,
        clientHeight / 2,
        Math.max(clientWidth, clientHeight) * 0.7,
      );
      vignette.addColorStop(0, 'rgba(0,0,0,0)');
      vignette.addColorStop(1, 'rgba(0,0,0,0.55)');
      ctx.fillStyle = vignette;
      ctx.fillRect(0, 0, clientWidth, clientHeight);

      if (progress < 1 && !finishedRef.current) {
        frameRef.current = requestAnimationFrame(render);
      } else {
        finishSequence();
      }
    };

    frameRef.current = requestAnimationFrame(render);

    return () => {
      finishedRef.current = true;
      cancelAnimationFrame(frameRef.current);
      window.removeEventListener('resize', resize);
    };
  }, [finishSequence]);

  useEffect(() => {
    const timer = setTimeout(() => {
      finishSequence();
    }, DURATION);
    return () => clearTimeout(timer);
  }, [finishSequence]);

  return (
    <div
      className={`fixed inset-0 z-40 overflow-hidden transition-opacity duration-500 ${
        fadeOut ? 'opacity-0 pointer-events-none' : 'opacity-100'
      }`}
    >
      <canvas ref={canvasRef} className="w-full h-full" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(255,214,153,0.06),transparent_45%)]" />
      <div className="absolute inset-0 flex flex-col items-center justify-end pb-16">
        <div
          className={`transition-all duration-700 text-center space-y-3 ${
            showTitle ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
          }`}
        >
          <p className="text-sm tracking-[0.4em] text-yellow-200/60 uppercase">Fuego y acero</p>
          <h2 className="intro-title text-4xl sm:text-5xl font-display tracking-[0.35em]">Batalla Medieval</h2>
        </div>
        <button
          type="button"
          className="pointer-events-auto mt-8 rounded-full border border-yellow-700/70 px-4 py-2 text-xs font-semibold tracking-[0.2em] text-yellow-100/90 bg-black/40 hover:bg-black/60 transition"
          onClick={finishSequence}
        >
          Saltar intro
        </button>
      </div>
    </div>
  );
};

export default IntroAnimation;
