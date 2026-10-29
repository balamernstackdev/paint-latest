# Troubleshooting Guide

## Common Issues and Solutions

### Installation Issues

#### Model Weights Not Found
**Problem**: Error message "SAM Model not found" on startup

**Solution**:
1. Ensure you have stable internet connection
2. Model auto-downloads on first run (may take 2-3 minutes)
3. If download fails, manually download from:
   ```
   https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth
   ```
4. Place file in project root directory
5. Restart application

#### Dependency Conflicts
**Problem**: Import errors or version conflicts

**Solution**:
```bash
# Create fresh virtual environment
python -m venv venv
source venv/bin/activate# Windows: venv\Scripts\activate

# Install exact versions
pip install -r requirements.txt
```

### Runtime Issues

####Canvas Not Responding
**Problem**: Clicks on canvas don't trigger segmentation

**Solutions**:
- **Desktop**: Ensure you're in "AI Click" or "AI Object" mode
- **Mobile**: Clear browser cache, reload page
- Check browser console for JavaScript errors (F12)
- Try different browser (Chrome/Firefox recommended)

#### Slow Performance
**Problem**: App is laggy or masks take long time

**Solutions**:
1. **Reduce Image Size**: Use images < 1100px (auto-resized)
2. **Clear Layers**: Too many layers slow composition
3. **Close Other Apps**: SAM uses significant CPU
4. **Check System Resources**: Monitor RAM usage

#### White Screen / Blank Display
**Problem**: Canvas shows white screen after paint

**Solutions**:
- Click "Reset View" button
- Refresh browser page (F5)
- Clear all layers and start fresh
- Check for errors in terminal/console

### Mobile-Specific Issues

#### Touch Not Working
**Problem**: Taps don't register on mobile

**Solutions**:
- Ensure JavaScript enabled in browser
- Try landscape mode for better accuracy
- Disable browser gesture navigation if conflicting
- Use two-finger pan for panning, single tap for selection

#### Sidebar Won't Close
**Problem**: Sidebar stuck open on mobile

**Solution**:
- Tap the close arrow (←) inside sidebar
- Refresh page if arrow not visible
- Landscape mode provides more space

#### Zoom Controls Hidden
**Problem**: Can't find zoom controls

**Solution**:
- Zoom controls are below canvas on mobile (<1024px width)
- On desktop (>1024px), they're in sidebar
- Responsive CSS hides/shows based on screen width

### Segmentation Issues

#### Paint Spills Outside Object
**Problem**: Mask extends beyond intended wall/object

**Solutions**:
1. Use "Small Objects" precision mode (Advanced Precision)
2. Click closer to object center
3. Try "AI Object (Drag Box)" for precise boundaries
4. Adjust using undo and repaint smaller area

#### Object Not Fully Covered
**Problem**: Mask doesn't cover entire wall

**Solutions**:
1. Switch to "Floors/Whole" precision mode
2. Click multiple times on different areas
3. Use "AI Object (Drag Box)" to cover full area
4. Paint in sections and layer them

#### Wrong Object Selected
**Problem**: Clicking wall selects adjacent object

**Solutions**:
- Click in center of target object
- Zoom in for precision (use zoom controls)
- Use "AI Object (Drag Box)" for manual selection
- Undo (⏪) and try different click point

### Color Issues

#### Color Looks Wrong
**Problem**: Applied color doesn't match preview

**Causes**:
- Lighting in original image affects final color
- LAB color transfer preserves shadows/highlights
- Monitor calibration differs from mobile screens

**Solutions**:
- Adjust intensity slider for lighter/darker
- Try "Compare Before/After" to verify
- Export high-res and view on calibrated display

#### Color Picker Not Changing
**Problem**: Selected color doesn't update

**Solution**:
- Color picker is in isolated fragment
- Change should be immediate
- Refresh if stuck
- Check session state wasn't cleared

### Export Issues

#### High-Res Export Fails
**Problem**: Error when preparing download

**Solutions**:
1. Ensure original image was uploaded (not pasted)
2. Reduce number of layers (try <5)
3. Check available RAM (large images need 2GB+)
4. Try smaller original image

#### Downloaded Image Quality Poor
**Problem**: Exported PNG looks pixelated

**Causes**:
- Original upload was low resolution
- Browser downscaled during upload

**Solutions**:
- Use high-quality source images (2MP+)
- Avoid screenshots; use original photos
- Check original file size before upload

### Browser Compatibility

**Recommended Browsers:**
- ✅ Chrome 90+ (best performance)
- ✅ Firefox 88+
- ✅ Safari 14+ (iOS/macOS)
- ⚠️ Edge 90+ (mostly works)
- ❌ IE 11 (not supported)

**Known Issues:**
- Safari iOS: Two-finger pan sometimes conflicts with page zoom
- Firefox: Occasional canvas render delay on large images
- Mobile Chrome: Back button may clear session

### Debug Mode

Enable debug logging:
```python
# In app.py, add at top:
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check logs in terminal for detailed error traces.

### Getting Help

1. Check browser console (F12 → Console tab)
2. Check terminal running Streamlit
3. Note error messages exactly
4. Try minimal reproduction (new image, single click)
5. Report issue with:
   - Browser and version
   - Image dimensions
   - Steps to reproduce
   - Error messages

### Performance Benchmarks

**Expected Performance:**
- Image Upload: <2s for 2MP image
- First Mask Generation: 3-5s (model load + inference)
- Subsequent Masks: 1-2s
- High-Res Export: 5-10s depending on layers
- Memory Usage: 500MB-2GB depending on image size

If significantly slower, check system resources and close other applications.
