document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-submit-form]").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector("[data-submit-button]");
      if (!button) return;
      button.disabled = true;
      button.classList.add("is-loading");
      const label = button.querySelector(".button-label");
      if (label) label.textContent = "正在启动…";
    });
  });

  document.querySelectorAll(".clickable-row[data-href]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("a, button, input, select")) return;
      window.location.href = row.dataset.href;
    });
  });

  document.querySelectorAll("[data-delete-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const taskName = form.dataset.taskName || "该任务";
      const confirmed = window.confirm(
        `确定删除“${taskName}”吗？相关采集记录将从数据库中永久删除。`
      );
      if (!confirmed) event.preventDefault();
    });
  });

  const taskSearch = document.querySelector("[data-task-search]");
  const statusFilter = document.querySelector("[data-status-filter]");
  const taskRows = [...document.querySelectorAll("[data-task-row]")];
  const taskEmpty = document.querySelector("[data-filter-empty]");
  const filterTasks = () => {
    const query = (taskSearch?.value || "").trim().toLowerCase();
    const status = statusFilter?.value || "";
    let visible = 0;
    taskRows.forEach((row) => {
      const matches = (!query || row.dataset.keyword.includes(query)) && (!status || row.dataset.status === status);
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    if (taskEmpty) taskEmpty.hidden = visible !== 0;
  };
  taskSearch?.addEventListener("input", filterTasks);
  statusFilter?.addEventListener("change", filterTasks);

  const commentSearch = document.querySelector("[data-comment-search]");
  const comments = [...document.querySelectorAll("[data-comment]")];
  const commentEmpty = document.querySelector("[data-comment-empty]");
  commentSearch?.addEventListener("input", () => {
    const query = commentSearch.value.trim().toLowerCase();
    let visible = 0;
    comments.forEach((comment) => {
      const matches = !query || comment.textContent.toLowerCase().includes(query);
      comment.hidden = !matches;
      if (matches) visible += 1;
    });
    if (commentEmpty) commentEmpty.hidden = visible !== 0;
  });

  document.querySelectorAll("[data-reply-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const expanded = button.getAttribute("aria-expanded") === "true";
      const replies = button.closest(".comment-replies").querySelectorAll("[data-reply-item]");
      replies.forEach((reply, index) => { reply.hidden = expanded && index >= 2; });
      button.setAttribute("aria-expanded", String(!expanded));
      button.firstChild.textContent = expanded
        ? `查看另外 ${button.dataset.moreCount} 条回复 `
        : "收起回复 ";
    });
  });

  const toast = document.querySelector("[data-toast]");
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        if (toast) {
          toast.textContent = "视频 ID 已复制";
          toast.classList.add("is-visible");
          window.setTimeout(() => toast.classList.remove("is-visible"), 1800);
        }
      } catch (_) {
        button.textContent = button.dataset.copy;
      }
    });
  });

  if (document.querySelector("[data-auto-refresh]")) {
    window.setTimeout(() => {
      if (document.visibilityState === "visible") window.location.reload();
    }, 5000);
  }
});
