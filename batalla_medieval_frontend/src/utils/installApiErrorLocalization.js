import axiosClient from '../api/axiosClient';
import { localizeAxiosError } from './apiError';

let installed = false;

export const installApiErrorLocalization = () => {
  if (installed) return;
  installed = true;
  axiosClient.interceptors.response.use(
    (response) => response,
    (error) => Promise.reject(localizeAxiosError(error)),
  );
};

installApiErrorLocalization();
