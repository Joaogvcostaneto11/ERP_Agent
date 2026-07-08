export function renderValue(block) {
  const card = document.createElement("div");
  card.className = "value-card";
  const label = document.createElement("div");
  label.className = "label";
  label.textContent = block.label;
  const value = document.createElement("div");
  value.className = "value";
  const formatted = typeof block.value === "number"
    ? block.value.toLocaleString()
    : String(block.value);
  value.textContent = block.unit ? `${formatted} ${block.unit}` : formatted;
  card.append(label, value);
  return card;
}
