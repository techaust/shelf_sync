const hex = { "ink-950":"#0D1613","ink-900":"#14231F","ink-750":"#111C18","ink-800":"#15211D","stone-50":"#F6F7F5","white":"#FFFFFF","mist":"#E4EBE7","verdigris-700":"#1E6B5C","verdigris-300":"#6CC4AE","tbLight":"#F2F2F2","tbDark":"#202020" };
const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const L = (h) => { const n = parseInt(h.slice(1), 16); return 0.2126*lin(n>>16)+0.7152*lin((n>>8)&255)+0.0722*lin(n&255); };
const cr = (a, b) => { const x = L(hex[a]), y = L(hex[b]); return ((Math.max(x,y)+0.05)/(Math.min(x,y)+0.05)).toFixed(2); };
for (const [f,b] of [["ink-900","white"],["verdigris-700","white"],["ink-900","tbLight"],["verdigris-700","tbLight"],["mist","tbDark"],["verdigris-300","tbDark"],["mist","ink-900"],["verdigris-300","ink-900"],["verdigris-700","ink-900"],["mist","ink-950"],["verdigris-300","ink-950"],["verdigris-700","stone-50"],["ink-900","stone-50"]]) console.log(f,"on",b,cr(f,b));
