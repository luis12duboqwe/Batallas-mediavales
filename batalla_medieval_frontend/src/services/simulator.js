import axiosClient from '../api/axiosClient';

export const SIMULATOR_TROOPS = [
  'Lancero Común',
  'Soldado de Acero',
  'Arquero Real',
  'Jinete Explorador',
  'Caballero Imperial',
  'Quebramuros',
  'Tormenta de Piedra',
];

export const simulateBattle = (payload) => axiosClient.post('/simulate/battle', payload);

export const fetchSimulationModifiers = () => axiosClient.get('/simulate/modifiers');
