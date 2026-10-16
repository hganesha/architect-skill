# Offline 3D viewer

`viewer_template.html` receives the canonical model and compiled boxes at the
`/*__MODEL_JSON__*/null` marker. The CLI escapes script data and titles. It needs
no network or external framework. WebGL 1 uses triangle arrays without optional
index extensions; a context/shader failure displays an explicit error.

Features: Z-up orbit, pan, zoom, automatic fit, per-level exploded floors and
visibility, roof toggle, ray/box picking, room metrics, and free WASD/QE walking.
Canvas backing dimensions are independent of its CSS size, including high-DPI
screens. Resizing only reallocates buffers when dimensions change. Transparent
parts are sorted and drawn after opaque parts without writing depth.

Walking does not enforce collision, navigation clearance or accessibility. This
viewer targets small concept buildings; it is not a large federated BIM viewer.
