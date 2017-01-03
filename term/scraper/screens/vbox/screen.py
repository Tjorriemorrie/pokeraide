import logging
from PIL import Image  #, ImageFilter, ImageGrab
import virtualbox

from scraper.screens.base import BaseScreen


class Vbox(BaseScreen):
    """Vbox screen provider"""
    # todo specify specific vm
    # todo control and monitor vm
    # todo handle multiple vms

    NAME = 'VirtualBox'

    def __init__(self):
        self.logger = logging.getLogger()
        self.logger.info('initialising screen...')
        self.vbox = virtualbox.VirtualBox()

        self.vm = self.vbox.machines[0]
        self.vm_session = self.vm.create_session()
        self.vm_res = self.vm_session.console.display.get_screen_resolution(0)

    # def start_vm(self):
    #     try:
    #         if self.control_name != 'Direct mouse control':
    #             self.vm = self.vbox.find_machine(self.control_name)
    #             self.session = self.vm.create_session()
    #     except Exception as e:
    #         self.logger.warning(str(e))

    def take_screen_shot(self):
        """Takes screen shot of display of vm"""
        png = self.vm_session.console.display.take_screen_shot_to_array(
            0, self.vm_res[0], self.vm_res[1], virtualbox.library.BitmapFormat.png)
        open('screenshot_vbox.png', 'wb').write(png)
        return Image.open('screenshot_vbox.png')


    # def mouse_move_vbox(self, x, y, dz=0, dw=0):
    #     self.session.console.mouse.put_mouse_event_absolute(x, y, dz, dw, 0)
    #
    # def mouse_click_vbox(self, x, y, dz=0, dw=0):
    #     self.session.console.mouse.put_mouse_event_absolute(x, y, dz, dw, 0b1)
    #     time.sleep(np.random.uniform(0.27, 0.4, 1)[0])
    #     self.session.console.mouse.put_mouse_event_absolute(x, y, dz, dw, 0)
    #
    # def get_mouse_position_vbox(self):
    #     # todo: not working
    #     x = self.session.console.mouse_pointer_shape.hot_x()
    #     y = self.session.console.mouse_pointer_shape.hot_y()
    #     return x, y
