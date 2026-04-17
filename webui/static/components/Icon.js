const SVG_DEFAULT_ATTRS = {
  xmlns: "http://www.w3.org/2000/svg",
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  "stroke-linecap": "round",
  "stroke-linejoin": "round",
};

function toPascalCase(name) {
  return String(name || "")
    .split(/[-_\s]+/g)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join("");
}

function renderNode(h, node) {
  if (typeof node === "string") return node;
  if (!Array.isArray(node)) return null;
  const [tag, attrs, children] = node;
  return h(
    tag,
    attrs || {},
    Array.isArray(children) ? children.map((child) => renderNode(h, child)) : null
  );
}

export const Icon = {
  name: "Icon",
  props: {
    name: { type: String, required: true },
    size: { type: [Number, String], default: 18 },
    strokeWidth: { type: [Number, String], default: 1.75 },
  },
  render() {
    const lib = typeof window !== "undefined" ? window.lucide || {} : {};
    const key = toPascalCase(this.name);
    const children = lib[key];
    if (!Array.isArray(children)) {
      return Vue.h("svg", {
        ...SVG_DEFAULT_ATTRS,
        width: this.size,
        height: this.size,
        "stroke-width": this.strokeWidth,
        class: "icon icon-missing",
        "aria-hidden": "true",
      });
    }
    const h = Vue.h;
    return h(
      "svg",
      {
        ...SVG_DEFAULT_ATTRS,
        width: this.size,
        height: this.size,
        "stroke-width": this.strokeWidth,
        class: "icon",
        "aria-hidden": "true",
      },
      children.map((child) => renderNode(h, child))
    );
  },
};
