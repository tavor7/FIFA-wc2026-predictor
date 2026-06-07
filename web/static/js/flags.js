/** Team flag URLs (mirrors backend team_flags.py). */
const TEAM_ISO = {
  Argentina: "ar", France: "fr", England: "gb-eng", Brazil: "br", Spain: "es",
  Germany: "de", Portugal: "pt", Netherlands: "nl", Belgium: "be", Croatia: "hr",
  Colombia: "co", Uruguay: "uy", Mexico: "mx", "United States": "us", Switzerland: "ch",
  Japan: "jp", Senegal: "sn", Morocco: "ma", Ecuador: "ec", Austria: "at", Norway: "no",
  Canada: "ca", "South Korea": "kr", Australia: "au", Paraguay: "py", Turkey: "tr",
  Sweden: "se", Tunisia: "tn", Egypt: "eg", Algeria: "dz", "Ivory Coast": "ci",
  Ghana: "gh", Cameroon: "cm", "Czech Republic": "cz", Scotland: "gb-sct", Wales: "gb-wls",
  Serbia: "rs", Poland: "pl", Ukraine: "ua", Denmark: "dk", "Costa Rica": "cr",
  Panama: "pa", "New Zealand": "nz", Iran: "ir", Qatar: "qa", "Saudi Arabia": "sa",
  Iraq: "iq", Jordan: "jo", Uzbekistan: "uz", "South Africa": "za", Nigeria: "ng",
  "Cape Verde": "cv", Curacao: "cw", Haiti: "ht", Honduras: "hn", Jamaica: "jm",
  Bolivia: "bo", Peru: "pe", Chile: "cl", "North Macedonia": "mk", Slovenia: "si",
  Slovakia: "sk", Romania: "ro", Hungary: "hu", Greece: "gr", Finland: "fi",
  Ireland: "ie", "Northern Ireland": "gb-nir", Israel: "il", Albania: "al",
  Georgia: "ge", Kosovo: "xk", Montenegro: "me", "Bosnia and Herzegovina": "ba",
};

export function slugify(name) {
  return (name || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function flagCode(name) {
  return TEAM_ISO[name] || null;
}

export function flagUrl(name, meta) {
  if (meta?.flag_url) return meta.flag_url;
  if (meta?.country_code) return `https://flagcdn.com/w40/${meta.country_code}.png`;
  const code = flagCode(name);
  return code ? `https://flagcdn.com/w40/${code}.png` : null;
}

export function teamInitials(name) {
  const words = (name || "?").trim().split(/\s+/);
  if (words.length >= 2) return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  return (name || "?").slice(0, 2).toUpperCase();
}

export function teamBadgeHtml(name, meta, size = "") {
  const url = flagUrl(name, meta);
  const cls = size ? `team-badge ${size}` : "team-badge";
  if (url) {
    return `<img class="${cls} flag-img" src="${url}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'${cls}',textContent:'${teamInitials(name)}'}))" />`;
  }
  return `<div class="${cls}">${teamInitials(name)}</div>`;
}

export function teamLinkHtml(name, meta) {
  const slug = meta?.slug || slugify(name);
  return `<a class="team-link" href="#/team/${slug}">${teamBadgeHtml(name, meta)}<span class="team-name">${escapeHtml(name)}</span></a>`;
}

export function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}
