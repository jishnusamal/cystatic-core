"""Language plugin registry."""

from core.errors import LanguageNotSupported, LanguageRegistrationError
from engine.language.base import BaseLanguageAdapter, LanguagePlugin, LanguageSpec


class LanguageRegistry:
    """Central registry and source of truth for installed language plugins.

    Maintains lookup indexes by language ID, file extension, and filename.
    """

    def __init__(self) -> None:
        """Initialize the language registry."""
        self._plugins_by_id: dict[str, LanguagePlugin] = {}
        self._plugins_by_ext: dict[str, LanguagePlugin] = {}
        self._plugins_by_filename: dict[str, LanguagePlugin] = {}

    def register(self, plugin: LanguagePlugin) -> None:
        """Register a language plugin and update lookup indexes.

        Args:
            plugin: The language plugin instance satisfying LanguagePlugin protocol.

        Raises:
            ValueError: If the plugin does not have a valid spec or has an empty ID.
            LanguageRegistrationError: If the language ID or any of its extensions/filenames is already registered.
        """
        if not hasattr(plugin, "spec") or not plugin.spec:
            raise ValueError("Plugin must have a valid spec")

        spec = plugin.spec
        if not spec.id:
            raise ValueError("Plugin spec must have a non-empty ID")

        # Check for duplicate ID
        if spec.id in self._plugins_by_id:
            raise LanguageRegistrationError(
                f"Language ID '{spec.id}' is already registered"
            )

        # Check for duplicate extensions
        for ext in spec.extensions:
            norm_ext = ext.lower()
            if norm_ext in self._plugins_by_ext:
                existing_id = self._plugins_by_ext[norm_ext].spec.id
                raise LanguageRegistrationError(
                    f"Extension '{ext}' is already registered by '{existing_id}'"
                )

        # Check for duplicate filenames
        for filename in spec.filenames:
            if filename in self._plugins_by_filename:
                existing_id = self._plugins_by_filename[filename].spec.id
                raise LanguageRegistrationError(
                    f"Filename '{filename}' is already registered by '{existing_id}'"
                )

        # Register plugin by ID
        self._plugins_by_id[spec.id] = plugin

        # Register by extension
        for ext in spec.extensions:
            self._plugins_by_ext[ext.lower()] = plugin

        # Register by filename
        for filename in spec.filenames:
            self._plugins_by_filename[filename] = plugin

    def get(self, language_id: str) -> LanguagePlugin:
        """Get a registered language plugin by its ID.

        Args:
            language_id: The ID of the language plugin (e.g. "python").

        Returns:
            The registered LanguagePlugin.

        Raises:
            LanguageNotSupported: If no plugin is registered with the given ID.
        """
        if language_id not in self._plugins_by_id:
            supported = list(self._plugins_by_id.keys())
            raise LanguageNotSupported(
                f"Language '{language_id}' is not supported. Supported languages: {supported}",
                details={"language": language_id, "supported": supported},
            )
        return self._plugins_by_id[language_id]

    def find_by_extension(self, extension: str) -> LanguagePlugin | None:
        """Find a registered language plugin by file extension (case-insensitive).

        Args:
            extension: The file extension (e.g. ".py").

        Returns:
            The matching LanguagePlugin or None.
        """
        if not extension:
            return None
        return self._plugins_by_ext.get(extension.lower())

    def find_by_filename(self, filename: str) -> LanguagePlugin | None:
        """Find a registered language plugin by exact filename.

        Args:
            filename: The filename (e.g. "Dockerfile").

        Returns:
            The matching LanguagePlugin or None.
        """
        return self._plugins_by_filename.get(filename)

    def specs(self) -> tuple[LanguageSpec, ...]:
        """Get specifications for all registered plugins.

        Returns:
            Tuple of LanguageSpec metadata objects.
        """
        return tuple(plugin.spec for plugin in self._plugins_by_id.values())

    def create_adapter(self, language_id: str) -> BaseLanguageAdapter:
        """Create a language adapter for the specified language.

        Args:
            language_id: The ID of the language (e.g. "python").

        Returns:
            An instance of BaseLanguageAdapter.

        Raises:
            LanguageNotSupported: If the language is not supported.
        """
        plugin = self.get(language_id)
        return plugin.create_adapter()

