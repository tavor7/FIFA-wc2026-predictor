import { escapeHtml } from "./flags.js";
import { matchCardHtml, section } from "./components.js";

function dateHeading(iso) {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso?.slice(0, 10) || "";
  }
}

function matchesByDay(matches) {
  const days = new Map();
  for (const m of matches) {
    const key = (m.date || "").slice(0, 10);
    if (!days.has(key)) days.set(key, []);
    days.get(key).push(m);
  }
  return [...days.entries()].sort(([a], [b]) => a.localeCompare(b));
}

function nextMatchesHtml(matches, phase) {
  if (!matches?.length) {
    return section(
      phase === "group_stage" ? "Next group matches" : "Upcoming knockout matches",
      `<p class="empty">No upcoming fixtures synced yet. Use <strong>Sync data</strong> on the home page.</p>`
    );
  }

  const title = phase === "group_stage" ? "Next group matches" : "Upcoming knockout matches";
  const grouped = matchesByDay(matches);
  const body = grouped
    .map(
      ([, dayMatches]) =>
        `<div class="ko-day">
          <h4 class="ko-day-title">${escapeHtml(dateHeading(dayMatches[0].date))}</h4>
          ${dayMatches.map((m) => matchCardHtml(m)).join("")}
        </div>`
    )
    .join("");

  return section(title, body);
}

function roundsHtml(rounds) {
  if (!rounds?.length) return "";
  return rounds
    .map((round) =>
      section(
        round.label,
        round.matches?.length
          ? round.matches.map((m) => matchCardHtml(m)).join("")
          : `<p class="empty">No fixtures in this round yet.</p>`
      )
    )
    .join("");
}

export function renderKnockoutBracket(data) {
  const phase = data.phase || "group_stage";
  const showNext = phase === "group_stage" || !data.has_knockout;

  return `<div class="ko-status">${escapeHtml(data.status || "")}</div>
    ${
      showNext
        ? `<p class="ko-hint">Standings and group tables are on the <a href="#/tournament">Groups</a> page.
          Match predictions are research estimates only.</p>
          ${nextMatchesHtml(data.next_matches, phase)}`
        : ""
    }
    ${data.has_knockout ? roundsHtml(data.rounds) : ""}
    ${
      data.has_knockout && data.next_matches?.length
        ? nextMatchesHtml(data.next_matches, "knockout")
        : ""
    }`;
}
