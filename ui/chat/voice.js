const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

export function isAvailable() {
  return typeof SR !== "undefined";
}

export function createRecognizer(lang) {
  const r = new SR();
  r.lang = lang || "pt-PT";
  r.continuous = false;
  r.interimResults = false;
  return r;
}
