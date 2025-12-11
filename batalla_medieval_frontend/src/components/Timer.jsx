import { useEffect, useState } from 'react';
import { formatDuration, timeRemaining } from '../utils/time';

const Timer = ({ endTime }) => {
  const [remaining, setRemaining] = useState(timeRemaining(endTime));

  useEffect(() => {
    const interval = setInterval(() => setRemaining(timeRemaining(endTime)), 1000);
    return () => clearInterval(interval);
  }, [endTime]);

  return <span className="text-yellow-400 font-mono">{formatDuration(remaining)}</span>;
};

export default Timer;
