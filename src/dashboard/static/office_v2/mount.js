// Single bundle entry — esbuild concatenates and transpiles these in
// order. The order matches the `<script>` tags in index.html:
//   tweaks-panel → sprites → props → scene → agent-motion → live-data → app
//
// React/ReactDOM are loaded via UMD <script> tags before this bundle,
// so the source files keep referring to globals `React` and `ReactDOM`.
// We pass them through here so esbuild's tree-shaker doesn't trim
// anything mistakenly.

import './tweaks-panel.jsx';
import './sprites.jsx';
import './props.jsx';
import './scene.jsx';
import './agent-motion.jsx';
import './live-data.jsx';
import './app.jsx';
