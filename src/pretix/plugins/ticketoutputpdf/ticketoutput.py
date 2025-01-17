import logging
from collections import OrderedDict
from io import BytesIO

from django import forms
from django.contrib.staticfiles import finders
from django.core.files import File
from django.http import HttpResponse
from django.utils.translation import ugettext_lazy as _

from pretix.base.ticketoutput import BaseTicketOutput
from pretix.control.forms import ExtFileField

logger = logging.getLogger('pretix.plugins.ticketoutputpdf')


class PdfTicketOutput(BaseTicketOutput):
    identifier = 'pdf'
    verbose_name = _('PDF output')
    download_button_text = _('Download PDF')
    download_button_icon = 'fa-print'

    def generate(self, request, order):
        from reportlab.graphics.shapes import Drawing
        from reportlab.pdfgen import canvas
        from reportlab.lib import pagesizes, units
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics import renderPDF
        from PyPDF2 import PdfFileWriter, PdfFileReader

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="order%s%s.pdf"' % (request.event.slug, order.code)

        pagesize = self.settings.get('pagesize', default='A4')
        if hasattr(pagesizes, pagesize):
            pagesize = getattr(pagesizes, pagesize)
        else:
            pagesize = pagesizes.A4
        orientation = self.settings.get('orientation', default='portrait')
        if hasattr(pagesizes, orientation):
            pagesize = getattr(pagesizes, orientation)(pagesize)

        fname = self.settings.get('background', as_type=File)
        if isinstance(fname, File):
            fname = fname.name
        else:
            fname = finders.find('pretixpresale/pdf/ticket_default_a4.pdf')

        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=pagesize)

        for op in order.positions.all().select_related('item', 'variation'):
            event_s = self.settings.get('event_s', default=22, as_type=float)
            if event_s:
                p.setFont("Helvetica", event_s)
                event_x = self.settings.get('event_x', default=15, as_type=float)
                event_y = self.settings.get('event_y', default=235, as_type=float)
                p.drawString(event_x * units.mm, event_y * units.mm, str(request.event.name))

            name_s = self.settings.get('name_s', default=17, as_type=float)
            if name_s:
                p.setFont("Helvetica", name_s)
                name_x = self.settings.get('name_x', default=15, as_type=float)
                name_y = self.settings.get('name_y', default=220, as_type=float)
                item = str(op.item.name)
                if op.variation:
                    item += " – " + str(op.variation)
                p.drawString(name_x * units.mm, name_y * units.mm, item)

            price_s = self.settings.get('price_s', default=17, as_type=float)
            if price_s:
                p.setFont("Helvetica", price_s)
                price_x = self.settings.get('price_x', default=15, as_type=float)
                price_y = self.settings.get('price_y', default=210, as_type=float)
                p.drawString(price_x * units.mm, price_y * units.mm, "%s %s" % (str(op.price), request.event.currency))

            qr_s = self.settings.get('qr_s', default=80, as_type=float)
            if qr_s:
                reqs = qr_s * units.mm
                qrw = QrCodeWidget(op.identity, barLevel='H')
                b = qrw.getBounds()
                w = b[2] - b[0]
                h = b[3] - b[1]
                d = Drawing(reqs, reqs, transform=[reqs / w, 0, 0, reqs / h, 0, 0])
                d.add(qrw)
                qr_x = self.settings.get('qr_x', default=10, as_type=float)
                qr_y = self.settings.get('qr_y', default=130, as_type=float)
                renderPDF.draw(d, p, qr_x * units.mm, qr_y * units.mm)

            code_s = self.settings.get('code_s', default=11, as_type=float)
            if code_s:
                p.setFont("Helvetica", code_s)
                code_x = self.settings.get('code_x', default=15, as_type=float)
                code_y = self.settings.get('code_y', default=130, as_type=float)
                p.drawString(code_x * units.mm, code_y * units.mm, op.identity)

            p.showPage()

        p.save()

        buffer.seek(0)
        new_pdf = PdfFileReader(buffer)
        output = PdfFileWriter()
        for page in new_pdf.pages:
            bg_pdf = PdfFileReader(open(fname, "rb"))
            bg_page = bg_pdf.getPage(0)
            bg_page.mergePage(page)
            output.addPage(bg_page)

        output.write(response)
        return response

    @property
    def settings_form_fields(self) -> dict:
        return OrderedDict(
            list(super().settings_form_fields.items()) + [
                ('paper_size',
                 forms.ChoiceField(
                     label=_('Paper size'),
                     choices=(
                         ('A4', 'A4'),
                         ('A5', 'A5'),
                         ('B4', 'B4'),
                         ('B5', 'B5'),
                         ('letter', 'Letter'),
                         ('legal', 'Legal'),
                     ),
                     required=False
                 )),
                ('orientation',
                 forms.ChoiceField(
                     label=_('Paper orientation'),
                     choices=(
                         ('portrait', _('Portrait')),
                         ('landscape', _('Landscape')),
                     ),
                     required=False
                 )),
                ('background',
                 ExtFileField(
                     label=_('Background PDF'),
                     ext_whitelist=(".pdf", ),
                     required=False
                 )),
                ('qr_x', forms.FloatField(label=_('QR-Code x position (mm)'), required=False)),
                ('qr_y', forms.FloatField(label=_('QR-Code y position (mm)'), required=False)),
                ('qr_s', forms.FloatField(label=_('QR-Code size (mm)'), required=False)),
                ('code_x', forms.FloatField(label=_('Ticket code x position (mm)'), required=False)),
                ('code_y', forms.FloatField(label=_('Ticket code y position (mm)'), required=False)),
                ('code_s', forms.FloatField(label=_('Ticket code size (mm)'), required=False)),
                ('name_x', forms.FloatField(label=_('Product name x position (mm)'), required=False)),
                ('name_y', forms.FloatField(label=_('Product name y position (mm)'), required=False)),
                ('name_s', forms.FloatField(label=_('Product name size (mm)'), required=False)),
                ('price_x', forms.FloatField(label=_('Price x position (mm)'), required=False)),
                ('price_y', forms.FloatField(label=_('Price y position (mm)'), required=False)),
                ('price_s', forms.FloatField(label=_('Price size (mm)'), required=False)),
                ('event_x', forms.FloatField(label=_('Event name x position (mm)'), required=False)),
                ('event_y', forms.FloatField(label=_('Event name y position (mm)'), required=False)),
                ('event_s', forms.FloatField(label=_('Event name size (mm)'), required=False)),
            ]
        )
