import React, { useState } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import LoadingScreen from './components/LoadingScreen.jsx';
import IntroAnimation from './components/IntroAnimation.jsx';
import './index.css';

const ExperienceShell = () => {
  const [introFinished, setIntroFinished] = useState(false);
  const [showLoading, setShowLoading] = useState(false);

  const handleIntroComplete = () => {
    setIntroFinished(true);
    setShowLoading(true);
  };

  const handleLoadingComplete = () => {
    setShowLoading(false);
  };

  return (
    <>
      {!introFinished && <IntroAnimation onComplete={handleIntroComplete} />}
      {showLoading && <LoadingScreen onComplete={handleLoadingComplete} />}
      <App />
    </>
  );
};

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ExperienceShell />
    </BrowserRouter>
  </React.StrictMode>
);
