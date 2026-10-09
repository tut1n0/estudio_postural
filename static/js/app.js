/* Estudio Postural - JS vanilla */

document.addEventListener('DOMContentLoaded', function () {
    // Toggle del sidebar en móvil
    var btn = document.getElementById('btnSidebar');
    var sidebar = document.getElementById('sidebar');
    if (btn && sidebar) {
        btn.addEventListener('click', function () {
            sidebar.classList.toggle('show');
        });
        document.addEventListener('click', function (e) {
            if (window.innerWidth < 992 && sidebar.classList.contains('show')
                && !sidebar.contains(e.target) && e.target !== btn) {
                sidebar.classList.remove('show');
            }
        });
    }

    // Confirmación genérica para formularios con data-confirmar
    document.querySelectorAll('form[data-confirmar]').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            if (!window.confirm(form.getAttribute('data-confirmar'))) {
                e.preventDefault();
            }
        });
    });

    // Al cambiar a estado "pagado" sugerir fecha de pago hoy
    var estado = document.querySelector('select[name="estado"]');
    var fechaPago = document.querySelector('input[name="fecha_pago"]');
    if (estado && fechaPago) {
        estado.addEventListener('change', function () {
            if (estado.value === 'pagado' && !fechaPago.value) {
                fechaPago.value = new Date().toISOString().slice(0, 10);
            }
        });
    }
});
