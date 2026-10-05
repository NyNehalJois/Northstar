document.querySelectorAll(".flash-dismiss").forEach((button) => {
  button.addEventListener("click", () => button.closest(".flash").remove());
});

document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

const themeOptions = document.querySelectorAll('input[name="theme"]');
if (themeOptions.length) {
  const savedTheme = localStorage.getItem("northstar-theme") || "system";
  const selectedTheme = [...themeOptions].find((option) => option.value === savedTheme);
  if (selectedTheme) selectedTheme.checked = true;

  const applyTheme = (preference) => {
    const followsDarkSystem = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme =
      preference === "dark" || (preference === "system" && followsDarkSystem) ? "dark" : "light";
  };

  themeOptions.forEach((option) => {
    option.addEventListener("change", () => {
      if (!option.checked) return;
      localStorage.setItem("northstar-theme", option.value);
      applyTheme(option.value);
      const status = document.querySelector("#theme-status");
      if (status) status.textContent = `${option.closest(".theme-option").querySelector("strong").textContent} theme saved on this device.`;
    });
  });

  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  systemTheme.addEventListener("change", () => {
    if ((localStorage.getItem("northstar-theme") || "system") === "system") applyTheme("system");
  });
}

const searchInput = document.querySelector("[data-table-search]");
if (searchInput) {
  const rows = [...document.querySelectorAll("[data-search-row]")];
  const emptyMessage = document.querySelector(".no-search-results");
  searchInput.addEventListener("input", () => {
    const query = searchInput.value.trim().toLocaleLowerCase();
    let visibleRows = 0;
    rows.forEach((row) => {
      const visible = row.textContent.toLocaleLowerCase().includes(query);
      row.hidden = !visible;
      if (visible) visibleRows += 1;
    });
    if (emptyMessage) emptyMessage.hidden = visibleRows > 0;
  });
}
