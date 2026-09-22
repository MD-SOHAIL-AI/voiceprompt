import React from 'react';
import ReactDOM from 'react-dom/client';
import { getCurrentWindow } from '@tauri-apps/api/window';
import App from './App';
import { Overlay } from './components/Overlay';
import './styles.css';

const root = ReactDOM.createRoot(document.getElementById('root')!);
const label = '__TAURI_INTERNALS__' in window ? getCurrentWindow().label : 'main';

root.render(
  <React.StrictMode>
    {label === 'overlay' ? <Overlay /> : <App />}
  </React.StrictMode>,
);
