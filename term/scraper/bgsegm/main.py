import cv2
import logging
import numpy as np
import os
from PIL import Image, ImageFilter, ImageEnhance, ImageOps

from scraper.screens.local.screen import Local


DIR = os.path.dirname(os.path.realpath(__file__))

logger = logging.getLogger()

# logger.info(dir(mog))
# logger.info('default learning rate = {}'.format(mog.getDefaultLearningRate()))
# mog.setBackgroundRatio(0.)
# logger.info('background ratio = {}'.format(mog.getBackgroundRatio()))
# input('>')

# gmg = cv2.bgsegm.createBackgroundSubtractorGMG()

logger.info('getting local images from {}'.format(Local.IMG_PATH))
files = []
for (dirpath, _, filenames) in os.walk(Local.IMG_PATH):
    for filename in filenames:
        if filename.startswith('.'):
            logger.debug('skipping {}'.format(filename))
            continue
        file_path = os.path.join(dirpath, filename)
        files.append(file_path)
logger.info('loaded {} images'.format(len(files)))

params = {
    'history': len(files),
    'nmixtures': 2,
    'backgroundRatio': 0.7,
    'noiseSigma': 1,
}

for i in range(11):
    params['history'] = i * 3
    # params['nmixtures'] = i
    # params['backgroundRatio'] = i * 4 / 100
    # params['noiseSigma'] = i * 3

    mog = cv2.bgsegm.createBackgroundSubtractorMOG(**params)
    logger.info('created mog with {}'.format(params))

    for file_path in files:
        # logger.info('file {}'.format(filename))

        img = Image.open(file_path)
        img = img.transpose(Image.ROTATE_90)
        img = img.convert('L')

        fg_mask = mog.apply(image=np.array(img))
        # bg = mog.getBackgroundImage()
        # cv2.imwrite(os.path.join(DIR, 'bg.png'), bg)

        # fg_mask = gmg.apply(np.array(img), 0.01)
        # cv2.imwrite(os.path.join(DIR, 'gmg.png'), fg_mask)

    img.save(os.path.join(DIR, 'img.png'))
    save_file = os.path.join(DIR, 'mog_{}.png'.format(i))

    cv2.imwrite(save_file, fg_mask)
    logger.info('saved image to {}'.format(save_file))
