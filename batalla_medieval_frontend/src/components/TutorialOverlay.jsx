import { useEffect, useState } from 'react';
import { useTutorialStore } from '../store/tutorialStore';
import { useUserStore } from '../store/userStore';
import { useNavigate } from 'react-router-dom';

const STEPS = [
  {
    id: 0,
    message: "¡Bienvenido, Señor! Tu aldea te espera. Revisa tus misiones para obtener recompensas iniciales.",
    target: "a[href='/quests']", 
    path: "/quests",
    action: "click"
  },
  {
    id: 1,
    message: "¡Tienes una recompensa lista! Reclámala para obtener recursos.",
    target: ".quest-claim-btn",
    path: "/quests",
    action: "click"
  },
  {
    id: 2,
    message: "Con recursos en mano, mejoremos nuestra infraestructura. Ve a Edificios.",
    target: "a[href='/buildings']",
    path: "/buildings",
    action: "click"
  },
  {
    id: 3,
    message: "Mejora tu Ayuntamiento o construye un Almacén para progresar.",
    target: ".upgrade-btn-ayuntamiento", 
    path: "/buildings",
    action: "click"
  },
  {
    id: 4,
    message: "¡Excelente! Ahora reclutemos algunas tropas para defendernos.",
    target: "a[href='/troops']",
    path: "/troops",
    action: "click"
  },
  {
    id: 5,
    message: "Aquí puedes entrenar soldados. Intenta reclutar un Infante.",
    target: ".recruit-btn-basic_infantry",
    path: "/troops",
    action: "click"
  },
  {
    id: 6,
    message: "¡Estás listo! Explora el mapa para encontrar enemigos.",
    target: "a[href='/map']",
    path: "/map",
    action: "click"
  }
];

const TutorialOverlay = () => {
  const { step, advance, fetchStatus, isActive } = useTutorialStore();
  const { isAuthenticated } = useUserStore(); // Import useUserStore
  const [coords, setCoords] = useState(null);

  useEffect(() => {
    if (isAuthenticated()) {
      fetchStatus();
    }
  }, [fetchStatus, isAuthenticated]);

  useEffect(() => {
    if (!isActive) return;
    
    const currentStep = STEPS.find(s => s.id === step);
    if (!currentStep) return;

    const updatePosition = () => {
      const element = document.querySelector(currentStep.target);
      if (element) {
        const rect = element.getBoundingClientRect();
        // Simple positioning logic: try right, if not enough space try left/bottom
        let top = rect.top + rect.height / 2 - 50;
        let left = rect.right + 20;
        
        if (left + 256 > window.innerWidth) {
            left = rect.left - 276; // 256 width + 20 padding
        }

        setCoords({ top, left });
        
        // Auto-advance listener
        const handleClick = () => {
            advance(step + 1);
        };
        element.addEventListener('click', handleClick, { once: true });
        
        return () => element.removeEventListener('click', handleClick);
      } else {
        setCoords(null);
      }
    };

    const interval = setInterval(updatePosition, 500);
    const cleanup = updatePosition();

    return () => {
        clearInterval(interval);
        if (cleanup) cleanup();
    };
  }, [step, isActive, advance]);

  if (!isActive || step >= STEPS.length) return null;

  const currentStep = STEPS.find(s => s.id === step);
  if (!currentStep || !coords) return null;

  return (
    <div className="fixed inset-0 z-50 pointer-events-none">
      <div 
        className="absolute bg-amber-900/95 text-amber-50 p-4 rounded-lg shadow-xl border border-amber-500 w-64 pointer-events-auto transition-all duration-300 backdrop-blur-sm"
        style={{ 
          top: coords.top, 
          left: coords.left 
        }}
      >
        <h3 className="font-bold mb-2 text-amber-300 flex justify-between">
            <span>Tutorial</span>
            <span className="text-xs bg-amber-950 px-2 py-0.5 rounded-full border border-amber-700">{step + 1}/{STEPS.length}</span>
        </h3>
        <p className="text-sm mb-4 leading-relaxed">{currentStep.message}</p>
        <button 
          onClick={() => advance(step + 1)}
          className="bg-amber-700 hover:bg-amber-600 text-white px-3 py-1.5 rounded text-xs w-full font-semibold transition-colors border border-amber-600"
        >
          Saltar paso
        </button>
      </div>
    </div>
  );
};

export default TutorialOverlay;
