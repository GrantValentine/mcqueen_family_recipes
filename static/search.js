// Fuse.js recipe search — loads search-index.json and wires up the nav search input
(function () {
  const input = document.getElementById("search-input");
  const results = document.getElementById("search-results");
  if (!input || !results) return;

  let fuse = null;

  fetch("/search-index.json")
    .then((r) => r.json())
    .then((data) => {
      fuse = new Fuse(data, {
        keys: ["title", "category", "snippet"],
        threshold: 0.35,
        minMatchCharLength: 2,
      });
    })
    .catch(() => {}); // silently fail in local file:// mode

  input.addEventListener("input", () => {
    const q = input.value.trim();
    results.innerHTML = "";

    if (!fuse || q.length < 2) {
      results.classList.add("hidden");
      return;
    }

    const hits = fuse.search(q).slice(0, 8);
    if (hits.length === 0) {
      results.classList.add("hidden");
      return;
    }

    hits.forEach(({ item }) => {
      const li = document.createElement("li");
      li.className = "px-3 py-2 hover:bg-amber-50 cursor-pointer border-b border-stone-100 last:border-0";
      li.innerHTML = `<div class="font-medium text-stone-800">${item.title}</div>`;
      li.addEventListener("click", () => {
        window.location.href = `/${item.category_slug}/${item.slug}/`;
      });
      results.appendChild(li);
    });

    results.classList.remove("hidden");
  });

  // Close on outside click
  document.addEventListener("click", (e) => {
    if (!input.contains(e.target) && !results.contains(e.target)) {
      results.classList.add("hidden");
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      results.classList.add("hidden");
      input.blur();
    }
  });
})();
