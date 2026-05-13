import React from 'react';
import { createRoot } from 'react-dom/client';
import OfficeApp from './app.jsx';
import { createOfficeDataProvider } from './data-provider.js';
import './styles.css';

let rootRef = null;

export function mountOfficeV2({ root, theme = 'dark', language = 'pt', dataProvider } = {}) {
  if (!root) return;
  if (rootRef) rootRef.unmount();
  rootRef = createRoot(root);
  rootRef.render(
    <OfficeApp
      theme={theme}
      language={language}
      dataProvider={dataProvider || createOfficeDataProvider()}
    />,
  );
}

export function unmountOfficeV2() {
  if (rootRef) {
    rootRef.unmount();
    rootRef = null;
  }
}

window.mountOfficeV2 = mountOfficeV2;
window.unmountOfficeV2 = unmountOfficeV2;
window.createOfficeDataProvider = createOfficeDataProvider;
