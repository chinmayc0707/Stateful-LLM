document.addEventListener('DOMContentLoaded', () => {
    // 1. Mobile Menu Toggle
    const mobileBtn = document.querySelector('.mobile-menu-btn');
    const mainNav = document.querySelector('.main-nav');

    mobileBtn.addEventListener('click', () => {
        mainNav.classList.toggle('active');

        // Toggle icon between bars and times (close)
        const icon = mobileBtn.querySelector('i');
        if (mainNav.classList.contains('active')) {
            icon.classList.remove('fa-bars');
            icon.classList.add('fa-times');
        } else {
            icon.classList.remove('fa-times');
            icon.classList.add('fa-bars');
        }
    });

    // 2. Mobile Mega-Menu Accordion
    const dropdownParent = document.querySelector('.has-dropdown > a');

    dropdownParent.addEventListener('click', (e) => {
        // Only prevent default and act as accordion if on mobile screen size
        if (window.innerWidth <= 768) {
            e.preventDefault();
            const parentLi = dropdownParent.parentElement;
            parentLi.classList.toggle('active');

            // Toggle arrow direction
            const arrow = dropdownParent.querySelector('i');
            if (parentLi.classList.contains('active')) {
                arrow.classList.remove('fa-chevron-down');
                arrow.classList.add('fa-chevron-up');
            } else {
                arrow.classList.remove('fa-chevron-up');
                arrow.classList.add('fa-chevron-down');
            }
        }
    });

    // Handle window resize to reset menu states
    window.addEventListener('resize', () => {
        if (window.innerWidth > 768) {
            mainNav.classList.remove('active');
            document.querySelector('.has-dropdown').classList.remove('active');

            const icon = mobileBtn.querySelector('i');
            icon.classList.remove('fa-times');
            icon.classList.add('fa-bars');

            const arrow = dropdownParent.querySelector('i');
            arrow.classList.remove('fa-chevron-up');
            arrow.classList.add('fa-chevron-down');
        }
    });

    // 3. Simple smooth scrolling for internal links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const targetId = this.getAttribute('href');

            // Skip if it's just '#'
            if (targetId === '#') return;

            const targetElement = document.querySelector(targetId);

            if (targetElement) {
                e.preventDefault();

                // Close mobile menu if open
                if (mainNav.classList.contains('active')) {
                    mobileBtn.click();
                }

                // Scroll to element accounting for fixed header
                const headerOffset = 80;
                const elementPosition = targetElement.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

                window.scrollTo({
                    top: offsetPosition,
                    behavior: "smooth"
                });
            }
        });
    });
});
