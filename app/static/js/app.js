// EventSphere Global Frontend Scripts

document.addEventListener("DOMContentLoaded", function () {
    // Check notifications if logged in
    fetchNotifications();

    // Start any active countdown timers on the page
    initCountdowns();
});

function fetchNotifications() {
    const notifBadge = document.getElementById("notif-badge");
    const notifList = document.getElementById("notif-list");
    if (!notifBadge || !notifList) return;

    fetch("/api/notifications/my")
        .then(res => {
            if (res.ok) return res.json();
            throw new Error("Not logged in");
        })
        .then(data => {
            const unread = data.filter(n => !n.is_read);
            if (unread.length > 0) {
                notifBadge.textContent = unread.length;
                notifBadge.classList.remove("d-none");
            } else {
                notifBadge.classList.add("d-none");
            }

            if (data.length === 0) {
                notifList.innerHTML = `<li class="dropdown-item text-muted text-center py-2">No notifications</li>`;
            } else {
                notifList.innerHTML = data.slice(0, 5).map(n => `
                    <li>
                        <a class="dropdown-item py-2 border-bottom ${n.is_read ? '' : 'bg-light fw-bold'}" href="#" onclick="markRead(${n.id})">
                            <div class="small text-truncate">${n.title}</div>
                            <div class="text-muted small text-truncate">${n.message}</div>
                        </a>
                    </li>
                `).join('');
            }
        })
        .catch(err => {
            // guest user, ignore
        });
}

function markRead(id) {
    fetch(`/api/notifications/${id}/read`, { method: "POST" })
        .then(() => fetchNotifications());
}

function initCountdowns() {
    document.querySelectorAll("[data-countdown]").forEach(el => {
        const targetDate = new Date(el.getAttribute("data-countdown")).getTime();
        const updateTimer = () => {
            const now = new Date().getTime();
            const distance = targetDate - now;

            if (distance < 0) {
                el.innerHTML = "<span class='badge bg-danger'>Expired</span>";
                return;
            }

            const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((distance % (1000 * 60)) / 1000);
            el.innerHTML = `${minutes}m ${seconds < 10 ? '0' : ''}${seconds}s remaining`;
        };

        updateTimer();
        setInterval(updateTimer, 1000);
    });
}
