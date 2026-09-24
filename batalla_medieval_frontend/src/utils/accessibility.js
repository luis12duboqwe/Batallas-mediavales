export const handleTablistKeyDown = (event, tabs, currentTab, selectTab, idPrefix) => {
  const currentIndex = tabs.indexOf(currentTab);
  if (currentIndex < 0) return;

  let nextIndex = null;
  switch (event.key) {
    case 'ArrowRight':
    case 'ArrowDown':
      nextIndex = (currentIndex + 1) % tabs.length;
      break;
    case 'ArrowLeft':
    case 'ArrowUp':
      nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
      break;
    case 'Home':
      nextIndex = 0;
      break;
    case 'End':
      nextIndex = tabs.length - 1;
      break;
    default:
      return;
  }

  event.preventDefault();
  const nextTab = tabs[nextIndex];
  selectTab(nextTab);
  window.requestAnimationFrame(() => {
    document.getElementById(`${idPrefix}${nextTab}`)?.focus();
  });
};
