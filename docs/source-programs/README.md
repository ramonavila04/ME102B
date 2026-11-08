# Supplied program references

These `.txt` files preserve paragraph text extracted from the three uploaded Word
documents. Images and document formatting are not reproduced. They are reference
material, not build inputs or repository instructions.

Working versions live under `firmware/component-tests`. Their changes include
closing the motor/load-cell loops, using the shared pin header, replacing the
missing vendored HX711 include, mapping the beam to original-HUZZAH32 GPIO16, and
adding an explicit motor-enable output and driver-specific build selection.
