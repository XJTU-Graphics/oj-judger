"""
函数提取模块

该模块负责使用 libclang 从 C++ 源文件中提取指定函数的完整实现。
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from clang.cindex import (
    Index, Cursor, CursorKind, Type, TranslationUnit,
    CompilationDatabase, CompileCommand
)
from judger.executor.function_types import FunctionSignature


logger = logging.getLogger('function_extractor')


class FunctionExtractor:
    """函数提取器类"""

    def __init__(self, build_dir: Path):
        """
        初始化函数提取器

        :param build_dir: 构建目录绝对路径，用于查找 compile_commands.json
        """
        self.index = Index.create()
        self.build_dir = build_dir
        self.compile_db: CompilationDatabase = CompilationDatabase.fromDirectory(build_dir)
        # 系统级 C/C++ 标准库搜索路径，libclang 不是完整编译器，所以需要手动指定这些路径
        self._system_include_paths: Optional[List[str]] = None
        # 将类型名称映射到 AST 中的类型对象以便和 AST 中的类型游标准确比较
        self._types: Dict[str, Type] = {}
        logger.info(f'FunctionExtractor instantiated from build dir {build_dir}')

    def _get_system_include_paths(self) -> List[str]:
        """
        获取 clang++ 的标准库 include path

        :return: 标准库 include path 列表
        :raises RuntimeError: 当无法获取 include path 时抛出
        """
        if self._system_include_paths is not None:
            return self._system_include_paths

        try:
            # 调用 clang++ 命令获取标准库搜索路径
            result = subprocess.run(
                ['clang++', '-E', '-x', 'c++', '-', '-v'],
                input='',
                capture_output=True,
                text=True,
                check=True
            )

            # 解析输出，提取 include path
            output = result.stderr

            # 查找包含路径的部分
            start_marker = '#include <...> search starts here:'
            end_marker = 'End of search list.'

            start_idx = output.find(start_marker)
            if start_idx == -1:
                raise RuntimeError('beginning of include paths not found in clang++ output')

            end_idx = output.find(end_marker, start_idx)
            if end_idx == -1:
                raise RuntimeError('end of include paths not found in clang++ output')

            # 提取路径部分
            paths_section = output[start_idx + len(start_marker):end_idx]

            # 按行分割并提取路径
            paths = []
            for line in paths_section.split('\n'):
                line = line.strip()
                if line and not line.startswith('ignoring nonexistent directory'):
                    paths.append(line)

            self._system_include_paths = paths
            return paths

        except subprocess.CalledProcessError as e:
            logger.error(f'failed to call clang++: {e}')
            raise RuntimeError(f'cannot find system include path: {e}') from e
        except Exception as e:
            logger.error(f'unexpected error occurred when finding system include path: {e}')
            raise RuntimeError(f'unexpected error occurred when finding include path: {e}') from e

    def _parse_types(
            self, type_names: List[str], source_file: Path, tu: TranslationUnit, args: List[str]
    ) -> None:
        """
        将类型名称在给定的翻译单元上下文中转换为 `clang.cindex.Type` 对象，
        保存解析得到的 `Type` 到 `self._types` 中以便进行严格的类型匹配。

        :param type_names: 所有要解析的类型名称
        :param source_file: 提供上下文的源文件
        :param tu: clang 翻译单元
        :param args: 用于解析 `source_file` 的编译参数
        """
        with source_file.open('r') as f:
            source_code = f.readlines()

        var_to_type = {}  # 临时变量名到类型名的映射
        logger.debug('following variable declarations are append to source file:')
        for i, type_name in enumerate(type_names):
            var_name = f'__judger_tmp_var_for_parse_{i}__'
            source_code.append(f'[[maybe_unused]] {type_name} {var_name};\n')  # 定义一个该类型的变量
            logger.debug(source_code[-1].strip())
            var_to_type[var_name] = type_name

        # 将上面的变量定义附加到源文件末尾得到一个临时文件，再解析这个文件得到类型
        filename = tu.spelling
        index = tu.index
        temp_tu = index.parse(
            path=filename,
            args=args,
            unsaved_files=[(filename, ''.join(source_code))]
        )
        for diag in temp_tu.diagnostics:
            logger.warning(diag)
        for cursor in temp_tu.cursor.walk_preorder():
            if cursor.spelling in var_to_type:
                type_name = var_to_type[cursor.spelling]
                logger.debug(
                    f'type {type_name} parsed to: {cursor.type.get_canonical().spelling}'
                )
                self._types[type_name] = cursor.type

    def extract_function_implementation(
        self,
        source_file_path: Path,
        function_signature: FunctionSignature
    ) -> Optional[str]:
        """
        从源文件中提取指定函数的实现

        :param source_file_path: 源文件绝对路径
        :param function_signature: 函数签名
        :return: 函数实现代码，如果未找到则返回None
        :raises RuntimeError: 当提取流程出现错误时抛出
        """
        try:
            # 查找编译命令
            compile_command: CompileCommand = self.compile_db.getCompileCommands(
                source_file_path
            )[0]

            if compile_command:
                # 使用编译命令解析源文件
                # 第一个参数是编译器，最后两个参数是源文件名，不应该传递给 libclang
                args = list(compile_command.arguments)[1:-2]

                # 添加系统 include path
                system_include_paths = self._get_system_include_paths()
                for path in system_include_paths:
                    args.extend(['-isystem', path])

                logger.debug(f'compilation args:\n{args}')
                tu = self.index.parse(str(source_file_path), args=args)
                logger.info(f'successfully parsed {source_file_path} to a translation unit')
                type_names = [function_signature.return_type]
                for param in function_signature.parameters:
                    type_names.append(param.type)
                logger.info(f'try to parse {len(type_names)} types')
                self._parse_types(type_names, source_file_path, tu, args)
                logger.info('successfully parsed all types in function signature')
            else:
                # 如果找不到编译命令，抛出异常报错
                logger.error(f'compile commands of {source_file_path} not found')
                raise RuntimeError(f'compile command not found for {source_file_path}')

            logger.info(f'try to match the signature of {function_signature.name}')
            # 查找匹配的函数定义
            function_cursor = self._find_function_signature(tu.cursor, function_signature)

            if function_cursor is None:
                logger.warning(
                    f'signature of {function_signature.name} does not match any source code'
                )
                return None
            else:
                logger.info('signature found')

            # 提取函数实现
            implementation = self._extract_function_body(function_cursor)

            if implementation:
                logger.info(f'successfully extracted implementation of {function_signature.name}')
            else:
                # 跳过函数声明之后，第二处签名匹配的位置仍然没有函数体
                logger.warning(
                    f'only declaration of {function_signature.name} found, no definition'
                )

            return implementation

        except RuntimeError:
            # 重新抛出 RuntimeError
            raise
        except Exception as e:
            # 其他异常转换为 RuntimeError 并抛出
            logger.error(
                f'unexpected error when extracting {function_signature.name}: {type(e)}: {str(e)}'
            )
            raise RuntimeError('failed to extract function implementation')

    def _find_function_signature(
        self,
        root_cursor: Cursor,
        function_signature: FunctionSignature
    ) -> Optional[Cursor]:
        """
        在AST中查找匹配的函数签名。因为第一个匹配结果必定是函数的声明，所以该函数会忽略它，
        返回第二个匹配成功的游标。

        :param root_cursor: AST根节点
        :param function_signature: 函数签名
        :return: 匹配成功的函数游标，如果未找到则返回 None
        """
        # 遍历AST查找函数定义
        for cursor in root_cursor.walk_preorder():
            if cursor.kind == CursorKind.FUNCTION_DECL or cursor.kind == CursorKind.CXX_METHOD:
                if self._is_function_match(cursor, function_signature):
                    # 如果一个翻译单元包含了这个函数的定义 (definition)，
                    # 那么其中一定先出现声明 (declaration) 才出现定义，所以需要跳过声明
                    body_cursor = None
                    for child in cursor.get_children():
                        if child.kind == CursorKind.COMPOUND_STMT:
                            body_cursor = child
                            break
                    if body_cursor is None:
                        # 这个函数没有函数体，只是一个声明而不是定义
                        continue
                    return cursor

        return None

    def _is_function_match(
        self,
        function_cursor: Cursor,
        function_signature: FunctionSignature
    ) -> bool:
        """
        检查函数是否与给定的函数签名匹配

        :param function_cursor: 函数定义节点
        :param function_signature: 函数签名
        :return: 是否匹配
        :raises ValueError: 当函数名称包含多个 :: 时抛出
        """
        # 检查函数名
        name = function_signature.name

        # 检查是否为类方法（包含 ::）
        if '::' in name:
            parts = name.split('::')

            # 如果有多个 ::，抛出异常
            if len(parts) > 2:
                raise ValueError('function name containing multiple \"::\" is not supported')

            class_name = parts[0]
            method_name = parts[1]

            # 对于类方法，需要满足两个条件：
            # 1. 当前 cursor 的 spelling 属性等于方法名
            # 2. 当前 cursor 的 semantic_parent 游标的 kind 为 CursorKind.CLASS_DECL 且其 spelling 等于类名
            if function_cursor.spelling != method_name:
                return False
            logger.debug(
                f'method name matched: {method_name} at line {function_cursor.location.line}'
            )

            # 检查父节点是否为类/结构体声明且类名匹配
            semantic_parent = function_cursor.semantic_parent
            if semantic_parent is not None:
                logger.debug(f'parent name: {semantic_parent.spelling}')
            if semantic_parent is None:
                return False
            if semantic_parent.kind not in [CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL]:
                return False
            if semantic_parent.spelling != class_name:
                return False
            logger.debug(f'class/struct name matched: {class_name}')
        else:
            # 普通函数，直接检查名称
            if function_cursor.spelling != name:
                return False
        logger.debug(f'function name matched: {name}')

        # 检查返回类型
        cursor_result_type_name = function_cursor.result_type.get_canonical().spelling
        signature_return_type = self._types[function_signature.return_type]
        signature_return_type_name = signature_return_type.get_canonical().spelling
        if cursor_result_type_name != signature_return_type_name:
            return False
        logger.debug(f'result type matched: {signature_return_type_name}')

        # 检查参数列表
        cursor_params = list(function_cursor.get_arguments())
        signature_params = function_signature.parameters

        if len(cursor_params) != len(signature_params):
            return False

        for cursor_param, signature_param in zip(cursor_params, signature_params):
            cursor_param_type_name = cursor_param.type.get_canonical().spelling
            signature_param_type = self._types[signature_param.type]
            signature_param_type_name = signature_param_type.get_canonical().spelling
            if cursor_param_type_name != signature_param_type_name:
                return False
            logger.debug(f'param type matched: {signature_param_type_name}')

        return True

    def _extract_function_body(self, function_cursor: Cursor) -> Optional[str]:
        """
        从函数定义节点中提取函数体

        :param function_cursor: 函数定义节点
        :return: 函数体代码，如果提取失败则返回None
        :raises RuntimeError: 当提取流程出现错误时抛出
        """
        try:
            # 获取函数体的范围
            body_cursor = None
            for child in function_cursor.get_children():
                if child.kind == CursorKind.COMPOUND_STMT:
                    body_cursor = child
                    break

            if body_cursor is None:
                logger.warning('the function cursor does not have a function body')
                return None

            # 获取源文件内容
            source_file = Path(function_cursor.location.file.name)
            if not source_file.is_absolute():
                source_file = self.build_dir.parent / source_file

            if not source_file.exists():
                raise RuntimeError(f'source file {source_file} not found')

            with open(source_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 获取函数体的起始和结束位置
            start_location = function_cursor.extent.start
            end_location = body_cursor.extent.end

            # 将从 1 开始的行号和列号转换成从 0 开始的下标，
            # 起始行/列、终止行/列所在的字符都包括在内
            start_line = start_location.line - 1
            start_column = start_location.column - 1
            end_line = end_location.line - 1
            end_column = end_location.column

            # 提取函数体
            if start_line == end_line:
                # 单行函数体
                function_body = lines[start_line][start_column:end_column]
            else:
                # 多行函数体
                function_body = [lines[start_line][start_column:] + '\n']
                for i in range(start_line + 1, end_line):
                    function_body.append(lines[i])
                function_body.append(lines[end_line][:end_column])
                function_body = ''.join(function_body)

            return function_body

        except Exception as e:
            logger.error(f'failed to extract function body: {type(e)}: {str(e)}')
            raise RuntimeError('failed to extract function body')


def extract_function_implementation(
    source_file_path: Path,
    function_signature: FunctionSignature,
    build_dir: Path
) -> Optional[str]:
    """
    从源文件中提取指定函数的实现

    :param source_file_path: 源文件绝对路径
    :param function_signature: 函数签名
    :param build_dir: 构建目录绝对路径，用于查找 compile_commands.json
    :return: 函数实现代码，如果未找到则返回None
    """
    extractor = FunctionExtractor(build_dir)
    return extractor.extract_function_implementation(source_file_path, function_signature)
